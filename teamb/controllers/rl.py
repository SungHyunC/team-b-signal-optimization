"""Reinforcement learning: tabular Q-learning, one policy shared by all four junctions.

Owner: AI & security (Yunseong). numpy only — no torch / stable-baselines.
Train with `python -m teamb.controllers.rl_train`; it writes models/rl_qtable.json.

Every `interval` (5 s), each junction that has shown green for `min_green` s picks
    action 0 = keep the green        action 1 = switch to the other axis

State, from loop detectors only (2 × 6 × 6 × 4 = 288 states):
    axis      which axis is green (EW / NS)
    serving   cars on the green axis' detectors (detector.count: still to be served)  6 buckets
    waiting   stopped cars on the red axis (detector.queue)                           6 buckets
    elapsed   seconds of green so far                                                 4 buckets

Reward every tick (5 s) for each junction:
    r = −(stopped cars on all four approaches) / reward_scale     and −switch_penalty for a switch
A decision lasts k ticks (until that junction can decide again), so the update is the
semi-MDP form of Q-learning:
    Q(s,a) ← Q(s,a) + α · [ R + γ^k · max_a' Q(s',a') − Q(s,a) ],   R = Σ_{i<k} γ^i · r_i

Rules around the policy (an action mask, not learned): never switch to an empty street;
always switch after `max_green` if the other street waits. Safety (min green, yellow,
all-red) stays with the supervisor. Stale / replayed observations → fixed-time fallback.

Low-confidence fallback (deploy mode only, `fallback_min_visits`, default 20): every reward
is negative, so every learned Q-value is below 0 while an action never tried keeps Q = 0 and
would win — the policy picked untrained actions out of distribution (special_event, the
flood). When the chosen action was seen fewer than `fallback_min_visits` times in training,
the junction follows the max-pressure rule (MaxPressureController defaults) instead. These
decisions are counted as `low_confidence_decisions` in the summary. 0 turns the fallback off
(the original behaviour). Training (learn=True) never falls back: it has to explore.

Model file: JSON with the Q-values, the feature definition and a SHA-256 checksum; loading
refuses a file whose checksum or features do not match (tampering / version drift).

Tunable: interval, min_green, max_green, model_path, fallback_min_visits; training knobs live
in rl_train.py.
Changing the bins (QUEUE_BINS, GREEN_BINS) changes the state space → retrain.
Upgrade path: SUMO-RL + DQN/PPO with richer state (docs/roles/ai-security.md).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from teamb import config
from teamb.controllers.base import Controller, register
from teamb.controllers.common import axis_sum, detector, num
from teamb.controllers.defense import ObservationGuard
from teamb.controllers.fixed_time import TimingPlan
from teamb.controllers.max_pressure import MaxPressureController
from teamb.fsutil import atomic_write_text
from teamb.sim.phases import AXES, other_axis

MODEL_PATH = config.MODELS / "rl_qtable.json"
QUEUE_BINS = (1, 3, 6, 10, 15)  # bucket edges in cars: 0 | 1-2 | 3-5 | 6-9 | 10-14 | 15+
GREEN_BINS = (15, 30, 50)  # bucket edges in seconds of green
FEATURES = {"queue_bins": list(QUEUE_BINS), "green_bins": list(GREEN_BINS), "axes": list(AXES),
            "state": ["axis", "serving_count", "waiting_queue", "green_elapsed"], "actions": ["keep", "switch"]}
N_Q, N_G = len(QUEUE_BINS) + 1, len(GREEN_BINS) + 1
N_STATES = len(AXES) * N_Q * N_Q * N_G
FORMAT = "teamb-rl-qtable/1"


def bucket(value: float, edges) -> int:
    return sum(value >= e for e in edges)


def encode_state(axis: str, serving: float, waiting: float, green_s: float) -> int:
    a, g, r, d = AXES.index(axis), bucket(serving, QUEUE_BINS), bucket(waiting, QUEUE_BINS), bucket(green_s, GREEN_BINS)
    return ((a * N_Q + g) * N_Q + r) * N_G + d


def decode_state(s: int) -> dict:
    s, d = divmod(s, N_G)
    s, r = divmod(s, N_Q)
    a, g = divmod(s, N_Q)
    return {"axis": AXES[a], "serving_bucket": g, "waiting_bucket": r, "green_bucket": d}


class QTable:
    """Q-values (states × 2 actions) plus visit counts and metadata, saved as JSON.

    `visits[s, a]` counts collected transitions (real experience, see count_visits). Files
    trained before that change (meta without "visit_unit") counted every replay update, up to
    sweeps × buffer (30×) more.
    """

    def __init__(self, q=None, visits=None, meta: dict | None = None):
        self.q = np.zeros((N_STATES, 2)) if q is None else np.asarray(q, dtype=float)
        self.visits = np.zeros((N_STATES, 2), dtype=int) if visits is None else np.asarray(visits, dtype=int)
        self.meta = dict(meta or {})
        if self.q.shape != (N_STATES, 2):
            raise ValueError(f"Q-table has shape {self.q.shape}, expected {(N_STATES, 2)} — retrain the model")

    def best(self, s: int) -> int:
        return int(self.q[s, 1] > self.q[s, 0])  # ties keep the green

    def update(self, s: int, a: int, reward: float, k: int, s2: int, alpha: float, gamma: float) -> None:
        """One Q-learning update. Does not touch `visits`: replaying a transition is not new experience."""
        target = reward + (gamma ** k) * self.q[s2].max()
        self.q[s, a] += alpha * (target - self.q[s, a])

    def count_visits(self, transitions) -> None:
        """Count real experience: once per collected (s, a, R, k, s') transition, never per replay."""
        for s, a, *_ in transitions:
            self.visits[s, a] += 1

    # --- file format ------------------------------------------------------------------
    def to_dict(self) -> dict:
        body = {"format": FORMAT, "features": FEATURES, "q": np.round(self.q, 4).tolist(), "visits": self.visits.tolist()}
        return {**body, "meta": self.meta, "sha256": _checksum(body)}

    @classmethod
    def from_dict(cls, data: dict) -> "QTable":
        if data.get("format") != FORMAT:
            raise ValueError(f"not a Q-table file (format {data.get('format')!r}, expected {FORMAT!r})")
        body = {k: data[k] for k in ("format", "features", "q", "visits")}
        if data.get("sha256") != _checksum(body):
            raise ValueError("Q-table checksum mismatch: the model file was modified or corrupted")
        if data["features"] != FEATURES:
            raise ValueError("Q-table was trained with different features; retrain with rl_train")
        return cls(data["q"], data["visits"], data.get("meta"))

    def save(self, path: Path | str = MODEL_PATH) -> Path:
        """Write the model atomically (temp file + rename): a crash never leaves a truncated model."""
        return atomic_write_text(path, json.dumps(self.to_dict(), separators=(",", ":")) + "\n")

    @classmethod
    def load(cls, path: Path | str = MODEL_PATH) -> "QTable":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                f"RL model not found at {path}. Train it first:  python -m teamb.controllers.rl_train"
            )
        return cls.from_dict(json.loads(path.read_text()))


def _checksum(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@register
class RLController(Controller):
    name = "rl"
    label = "Reinforcement learning (Q-table)"
    description = (
        "Tabular Q-learning trained on rush hour: every 5 s each junction keeps or switches its green "
        "from detector queues; one shared policy, safety stays with the supervisor."
    )
    owner = "AI & security (Yunseong)"
    observation_source = "detector"

    def __init__(
        self,
        model_path: str | None = None,
        interval: float = 5.0,
        min_green: float = 10.0,
        max_green: float = 60.0,
        epsilon: float = 0.0,
        learn: bool = False,
        gamma: float = 0.9,
        reward_scale: float = 10.0,
        switch_penalty: float = 0.2,
        max_obs_age: float = 10.0,
        fallback_min_visits: int = 20,
        **params,
    ):
        super().__init__(model_path=model_path, interval=interval, min_green=min_green, max_green=max_green,
                         epsilon=epsilon, learn=learn, gamma=gamma, reward_scale=reward_scale,
                         switch_penalty=switch_penalty, max_obs_age=max_obs_age,
                         fallback_min_visits=fallback_min_visits, **params)
        self.model_path = Path(model_path) if model_path else MODEL_PATH
        self.interval = float(interval)
        self.min_green = max(float(min_green), float(config.MIN_GREEN_S))
        self.max_green = float(max_green)
        self.epsilon = float(epsilon)
        self.learn = bool(learn)
        self.gamma = float(gamma)
        self.reward_scale = float(reward_scale)
        self.switch_penalty = float(switch_penalty)
        self.max_obs_age = float(max_obs_age)
        self.fallback_min_visits = int(fallback_min_visits)
        self.table: QTable | None = None  # loaded in reset(); the trainer may set it before

    def reset(self, cfg, seed, topology) -> None:
        super().reset(cfg, seed, topology)
        if self.table is None:
            self.table = QTable.load(self.model_path)
        self.rng = np.random.default_rng(seed + 12345)
        self.guard = ObservationGuard(topology, max_age_s=self.max_obs_age)
        self.fallback_plan = TimingPlan(splits={j: 0.5 for j in topology.tls_ids})
        self.memory: dict[str, dict | None] = {j: None for j in topology.tls_ids}  # last decision per junction
        self.transitions: list[tuple] = []  # (s, a, R, k, s') when learn=True
        self.episode_reward = 0.0
        self.decisions = 0
        self.low_confidence = 0  # decisions handed to the max-pressure rule (too little training data)
        self.rule = MaxPressureController()  # the low-confidence fallback
        self.rule.reset(cfg, seed, topology)
        self._degraded: str | None = None

    # --- the step -----------------------------------------------------------------
    def propose_action(self, state: dict) -> dict[str, str | None]:
        t = state["t"]
        if self._is_tick(t):
            self._degraded = self.guard.check_observation(self.observation, t)
            if not self._degraded:
                return self._tick(state)
        if self._degraded:
            return {j: self.fallback_plan.axis_at(j, t) for j in state["junctions"]}
        return {}

    def _is_tick(self, t: float) -> bool:
        k = t / self.interval
        return abs(k - round(k)) < 1e-6

    def _tick(self, state: dict) -> dict[str, str]:
        action: dict[str, str] = {}
        seen = self.observation["junctions"]
        for j, js in state["junctions"].items():
            approaches = seen.get(j, {}).get("approaches", {})
            r = -sum(num(detector(e), "queue") for e in approaches.values()) / self.reward_scale
            self.episode_reward += r
            mem = self.memory.get(j)
            if mem is not None:  # reward for the decision still running at J
                mem["R"] += (self.gamma ** mem["k"]) * r
                mem["k"] += 1
            if not js["green"] or js["time_in_state"] < self.min_green or not approaches:
                continue
            axis, green_s = js["phase"], js["time_in_state"]
            other = other_axis(axis)
            waiting = axis_sum(approaches, other, "queue")
            if waiting <= 0 and axis_sum(approaches, other, "count") <= 0:
                continue  # mask: never switch to an empty street
            if green_s >= self.max_green:
                action[j] = other  # mask: the other street has waited long enough
                continue
            s = encode_state(axis, axis_sum(approaches, axis, "count"), waiting, green_s)
            if mem is not None and self.learn:
                self.transitions.append((mem["s"], mem["a"], round(mem["R"], 5), mem["k"], s))
            a = self._choose(s)
            if not self.learn and self.table.visits[s, a] < self.fallback_min_visits:
                a = self._rule_action(j, axis, green_s)  # too little training data for this choice
                self.low_confidence += 1
            self.decisions += 1
            self.memory[j] = {"s": s, "a": a, "R": -self.switch_penalty if a else 0.0, "k": 0}
            if a == 1:
                action[j] = other
        return action

    def summary(self) -> dict:
        meta = self.table.meta if self.table else {}
        model = {k: meta.get(k) for k in ("episodes", "trained_unix", "wall_minutes", "scenario")}
        model["visit_unit"] = meta.get("visit_unit", "replay_updates")
        return {"decisions": self.decisions, "low_confidence_decisions": self.low_confidence,
                "low_confidence_share": round(self.low_confidence / self.decisions, 4) if self.decisions else 0.0,
                "fallback_min_visits": self.fallback_min_visits,
                "guard_rejected": dict(self.guard.rejected), "model": model}

    def _choose(self, s: int) -> int:
        if self.learn and self.rng.random() < self.epsilon:
            return int(self.rng.integers(2))
        return self.table.best(s)

    def _rule_action(self, junction: str, axis: str, green_s: float) -> int:
        """The max-pressure decision for this junction, as an action (0 keep / 1 switch)."""
        self.rule.observation = self.observation
        return int(self.rule.decide(junction, axis, green_s) == other_axis(axis))
