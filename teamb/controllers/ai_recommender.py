"""AI timing-plan recommender with engineer approval (Google "Project Green Light" style).

Owner: AI & security (Yunseong).

    1. Run the current plan (fixed-time 90 s, 50/50) — the AI never drives the signals itself.
    2. Collect navigation-app probe data only (demand_model.py; no loop detectors, no ground truth).
    3. At `search_at` (or on an "optimize" command): estimate the demand, then search cycle,
       EW split and offsets with Optuna by simulating that estimated demand (optimizer.py).
    4. Publish the best plan as a recommendation with its expected improvement.
    5. An engineer approves ("approve") or rejects ("reject"); only an approved plan is applied.
       `auto_approve=True` approves automatically (batch experiments).

Modes: async (default for the live twin) runs the search in a spawned worker process and
polls it from `log()`, so the simulation never waits. sync (default when auto_approve) runs
the search inside `log()` — outside the controller's 0.25 s budget, which only covers
observe/propose_action — so batch results do not depend on wall-clock speed.

Recommendation (pending_recommendation(), also shown as frame["recommendation"]):
    {"id", "status": "searching" | "pending" | "approved" | "rejected", "created_t",
     "plan": {"cycle", "splits": {J: share}, "offsets": {J: s}} | null while searching,
     "current_plan": {...},
     "expected": {"mean_delay_s", "baseline_mean_delay_s", "improvement_pct", ...} | null,
     "based_on": {"coverage", "window_s", "trials", "estimated_flows": {J: {side: veh/h}}, ...},
     "progress": {"done", "total"}, "note", "error", "decided_by", "decided_t"}
A failed search is reported as status "rejected" with decided_by "system" and an "error".

Commands (handle_command): {"type": "approve", "id"}, {"type": "reject", "id"}, {"type": "optimize"}.
With `approval_token` set, approve/reject must carry the same "token" (a stand-in for the
role-based permission an operator UI would enforce); every decision goes to `self.audit`.

Tunable: auto_approve, search_at, trials, eval_horizon, eval_warmup, window_s, defense
(ignore untrusted probe data), sync, cache (True / False / directory), approval_token.
"""
from __future__ import annotations

import copy
import hmac
from dataclasses import asdict

from teamb import config
from teamb.controllers.base import Controller, register
from teamb.controllers.defense import ObservationGuard
from teamb.controllers.demand_model import ProbeDemandModel, nested, od_flows
from teamb.controllers.fixed_time import TimingPlan
from teamb.controllers import optimizer


@register
class AIRecommenderController(Controller):
    name = "ai_recommender"
    label = "AI recommender (engineer approves)"
    description = (
        "Learns demand from navigation-app probes only, searches a better timing plan in simulation "
        "(Optuna), and applies it after an engineer approves — like Google's Project Green Light."
    )
    owner = "AI & security (Yunseong)"
    observation_source = "probe"

    def __init__(
        self,
        auto_approve: bool = False,
        search_at: float | None = 600.0,
        trials: int = 30,
        eval_horizon: float = 900.0,
        eval_warmup: float = 300.0,
        window_s: float = 300.0,
        defense: bool = False,
        sync: bool | None = None,
        cache: bool | str = True,
        approval_token: str | None = None,
        cycle: float = config.BASE_CYCLE_S,
        split: float = 0.5,
        **params,
    ):
        super().__init__(auto_approve=auto_approve, search_at=search_at, trials=trials, eval_horizon=eval_horizon,
                         eval_warmup=eval_warmup, window_s=window_s, defense=defense, sync=sync, cache=cache,
                         cycle=cycle, split=split, **params)
        self.auto_approve = bool(auto_approve)
        self.search_at = None if search_at is None else float(search_at)
        self.trials = int(trials)
        self.eval_horizon = float(eval_horizon)
        self.eval_warmup = float(eval_warmup)
        self.window_s = float(window_s)
        self.defense = bool(defense)
        self.sync = self.auto_approve if sync is None else bool(sync)
        self.cache_dir = None if cache is False else (optimizer.CACHE_DIR if cache is True else cache)
        self._token = approval_token  # kept out of self.params so it never lands in a manifest
        self.cycle, self.split = float(cycle), float(split)
        self._job = None

    # --- lifecycle --------------------------------------------------------------
    def reset(self, cfg, seed, topology) -> None:
        super().reset(cfg, seed, topology)
        self.close()  # a previous run's search, if any
        self.plan = TimingPlan(cycle=self.cycle, splits={j: self.split for j in topology.tls_ids})
        self.guard = ObservationGuard(topology)
        self.demand = ProbeDemandModel(topology, window_s=self.window_s, defense=self.defense, guard=self.guard)
        self.lanes = {(j, s): len(lanes) for j, sides in topology.approach_lanes.items() for s, lanes in sides.items()}
        self.recommendation: dict | None = None
        self.history: list[dict] = []  # every recommendation of this run
        self.audit: list[dict] = []  # every approve / reject / optimize command
        self.events: list[dict] = []  # e.g. recommendation_ready, plan_applied (see report)
        self.t = 0.0
        self._due = self.search_at  # sim time of the next automatic search
        self._optimize_requested = False
        self._seq = 0

    def close(self) -> None:
        if self._job is not None:
            self._job.cancel()
            self._job = None

    # --- every step -----------------------------------------------------------------
    def observe(self, observation: dict) -> None:
        """Feed fresh probe data to the demand model.

        The controller's clock (`self.t`) follows the simulation (propose_action's state["t"]),
        never the observation's own timestamp: an observation older than the clock by more than
        the guard's max age is "stale" (frozen feed), one older than the last accepted is
        "replayed". Neither reaches the demand model, and neither can move the clock backwards.
        """
        super().observe(observation)
        if observation and observation.get("t") is not None:
            now = max(self.t, float(observation["t"]))
            if self.guard.check_observation(observation, now) is None:  # fresh, not replayed
                self.demand.add(observation)

    def propose_action(self, state: dict) -> dict[str, str | None]:
        t = state["t"]
        self.t = max(self.t, float(t))  # the simulation clock; only moves forward
        return {j: self.plan.axis_at(j, t) for j in state["junctions"]}

    def log(self, step: int) -> None:
        """Heavy work happens here, outside the controller's time budget."""
        if self._job is not None:
            self._poll()
        elif self._optimize_requested or (self._due is not None and self.t >= self._due):
            self._optimize_requested = False
            self._due = None
            self._start_search()
        return None

    # --- twin hooks -----------------------------------------------------------------------
    def pending_recommendation(self) -> dict | None:
        return copy.deepcopy(self.recommendation)

    def handle_command(self, command: dict) -> dict | None:
        kind = command.get("type")
        if kind == "optimize":
            if self._job is not None or (self.recommendation or {}).get("status") == "searching":
                return {"ok": False, "error": "a search is already running"}
            self._optimize_requested = True
            self._audit(kind, command, ok=True)
            return {"ok": True, "status": "searching", "message": "the search starts at the next simulation step"}
        if kind not in ("approve", "reject"):
            return None  # not ours: the env reports "unknown command"
        rec = self.recommendation
        if self._token is not None and not hmac.compare_digest(str(command.get("token", "")), self._token):
            self._audit(kind, command, ok=False)
            return {"ok": False, "error": "not authorized (approval token missing or wrong)"}
        if rec is None or rec["status"] != "pending":
            return {"ok": False, "error": "no recommendation is waiting for approval"}
        if command.get("id") not in (None, rec["id"]):
            return {"ok": False, "error": f"recommendation {command.get('id')} is not the pending one ({rec['id']})"}
        who = str(command.get("by", "engineer"))
        if kind == "approve":
            self._apply(rec, who)
        else:
            rec.update(status="rejected", decided_by=who, decided_t=self.t)
        self._audit(kind, command, ok=True)
        return {"ok": True, "id": rec["id"], "status": rec["status"], "plan": rec["plan"]}

    def summary(self) -> dict:
        """For experiments: every recommendation of the run and how the probe data looked."""
        keep = ("id", "status", "created_t", "plan", "expected", "note", "error", "decided_by", "decided_t")
        return {"recommendations": [{k: r.get(k) for k in keep} for r in self.history],
                "ignored_untrusted": self.demand.ignored, "audit": list(self.audit)}

    def drain_events(self) -> list[dict]:
        events, self.events = self.events, []
        return events

    # --- search ------------------------------------------------------------------------------
    def _start_search(self) -> None:
        demand = self.demand.approach_demand(self.t)
        flows = od_flows(demand, self.topology.tls_ids)
        seeds = [optimizer.webster_plan(demand, self.lanes, green_wave=True),
                 optimizer.webster_plan(demand, self.lanes, green_wave=False)]
        spec = optimizer.SearchSpec(
            flows=[asdict(f) for f in flows],
            current=self.plan.to_dict(),
            seed_plans=[p.to_dict() for p in seeds],
            junctions=list(self.topology.tls_ids),
            trials=self.trials,
            eval_warmup=self.eval_warmup,
            eval_horizon=self.eval_horizon,
            sampler_seed=self.seed,
        )
        self._seq += 1
        self.recommendation = {
            "id": f"rec{self._seq}-t{int(self.t)}",
            "status": "searching",
            "created_t": self.t,
            "plan": None,
            "current_plan": self.plan.to_dict(),
            "expected": None,
            "based_on": {
                "coverage": self.demand.coverage,
                "window_s": self.window_s,
                "trials": self.trials,
                "estimated_flows": nested(demand),
                "probe_samples": len(self.demand.window(self.t)),
                "ignored_untrusted": self.demand.ignored,
                "defense": self.defense,
                "source": "navigation-app probes only",
            },
            "progress": {"done": 0, "total": self.trials + 1},
            "note": "",
            "error": None,
            "decided_by": None,
            "decided_t": None,
        }
        self.history.append(self.recommendation)
        self._spec = spec
        cached = optimizer.load_cache(spec, self.cache_dir) if self.cache_dir else None
        if cached is not None:
            self._finish(cached, cached=True)
            return
        if not self.sync:
            try:
                self._job = optimizer.SearchJob(spec)
                return
            except (AssertionError, OSError) as exc:  # e.g. inside a daemonic worker: search here instead
                self.recommendation["note"] = f"background search unavailable ({exc}); searched synchronously"
        try:
            result = optimizer.run_search(spec, progress=self._progress)
        except Exception as exc:  # a failed search must never stop the simulation
            self._fail(f"{type(exc).__name__}: {exc}")
            return
        self._finish(result)

    def _progress(self, done: int, total: int, best: float | None = None) -> None:
        if self.recommendation is not None:
            self.recommendation["progress"] = {"done": int(done), "total": int(total)}

    def _poll(self) -> None:
        for message in self._job.poll():
            kind = message[0]
            if kind == "progress":
                self._progress(*message[1:])
            elif kind == "result":
                self._job = None
                self._finish(message[1])
                return
            elif kind == "error":
                self._job = None
                self._fail(message[1])
                return

    def _fail(self, error: str) -> None:
        """The search failed: keep the current plan and say why."""
        self.recommendation.update(status="rejected", error=error, decided_by="system", decided_t=self.t)
        self.events.append({"t": self.t, "type": "recommendation_failed", "id": self.recommendation["id"], "error": error})

    def _finish(self, result: dict, cached: bool = False) -> None:
        rec = self.recommendation
        if self.cache_dir and not cached:
            optimizer.save_cache(self._spec, result, self.cache_dir)
        total = rec["progress"]["total"]
        rec.update(
            status="pending",
            plan=result["plan"],
            expected=result["expected"],
            progress={"done": total, "total": total},
            note=(rec["note"] + " " + result.get("note", "")).strip() + (" (from cache)" if cached else ""),
            search={"trials": result.get("trials"), "wall_s": result.get("wall_s"), "top_trials": result.get("top_trials", [])},
        )
        self.events.append({"t": self.t, "type": "recommendation_ready", "id": rec["id"],
                            "improvement_pct": rec["expected"]["improvement_pct"]})
        if self.auto_approve:
            self._apply(rec, "auto_approve")

    def _apply(self, rec: dict, who: str) -> None:
        self.plan = optimizer.plan_from_dict(rec["plan"])
        rec.update(status="approved", decided_by=who, decided_t=self.t)
        self.events.append({"t": self.t, "type": "plan_applied", "id": rec["id"], "plan": rec["plan"]})

    def _audit(self, kind: str, command: dict, ok: bool) -> None:
        self.audit.append({"t": self.t, "type": kind, "id": command.get("id"), "by": command.get("by"), "ok": ok})
