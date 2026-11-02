"""Independent safety supervisor — every controller action goes through here.

Controllers only *propose* a green axis per junction. The supervisor
- rejects malformed or unknown proposals and logs why (SIG-02),
- holds a green for at least MIN_GREEN_S before a switch,
- always runs yellow → all-red between greens,
- lets emergency-vehicle preemption cut a green after PREEMPT_MIN_GREEN_S, still with yellow and all-red,
- records every phase change for the data team's signal-event table.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from teamb import config
from teamb.sim.phases import AXES, NEXT_SIGNAL, axis_of, green_signal


@dataclass
class JunctionSignal:
    signal: str = "EW_G"
    t_in: float = 0.0  # seconds the current signal state has been shown
    phase_start: float = 0.0
    requested: str | None = None  # last valid request (EW/NS) that is not served yet
    preempted_by: str | None = None


@dataclass
class SignalEvent:
    t: float
    junction: str | None
    requested: str | None
    executed: str | None
    reason: str
    detail: str = ""


@dataclass
class SafetySupervisor:
    junction_ids: list[str]
    min_green: float = config.MIN_GREEN_S
    preempt_min_green: float = config.PREEMPT_MIN_GREEN_S
    yellow: float = config.YELLOW_S
    all_red: float = config.ALL_RED_S
    junctions: dict[str, JunctionSignal] = field(default_factory=dict)
    events: list[SignalEvent] = field(default_factory=list)
    rejections: int = 0

    def __post_init__(self):
        if not self.junctions:
            self.junctions = {j: JunctionSignal() for j in self.junction_ids}

    # --- controller interface -------------------------------------------
    def validate(self, action, t: float) -> dict[str, str]:
        """Return the valid part of a proposal ({junction: 'EW'|'NS'}); log the rest."""
        if action is None:
            return {}
        if not isinstance(action, dict):
            self._reject(t, None, repr(action)[:40], "action must be a dict {junction: 'EW'|'NS'|None}")
            return {}
        safe = {}
        for j, phase in action.items():
            if j not in self.junctions:
                self._reject(t, j, phase, "unknown junction")
            elif phase is None or phase == "keep":
                continue
            elif phase not in AXES:
                self._reject(t, j, phase, "invalid phase (expected 'EW' or 'NS')")
            else:
                safe[j] = phase
        return safe

    def apply_safe_action(self, safe: dict[str, str], t: float, preempt: dict[str, str] | None = None) -> dict[str, str]:
        """Advance every junction's state machine for this step and return its signal state."""
        preempt = preempt or {}
        for j, js in self.junctions.items():
            want = preempt.get(j) or safe.get(j)
            is_preempt = j in preempt
            js.requested = want
            js.preempted_by = preempt.get(j)
            self._advance(j, js, want, t, is_preempt)
        return {j: js.signal for j, js in self.junctions.items()}

    def tick(self, dt: float) -> None:
        for js in self.junctions.values():
            js.t_in += dt

    # --- state machine ----------------------------------------------------
    def _advance(self, j: str, js: JunctionSignal, want: str | None, t: float, is_preempt: bool) -> None:
        part = js.signal[3:]
        if part == "Y" and js.t_in >= self.yellow:
            self._set(j, js, NEXT_SIGNAL[js.signal], t, "yellow_done")
        elif part == "AR" and js.t_in >= self.all_red:
            self._set(j, js, NEXT_SIGNAL[js.signal], t, "all_red_done")
            js.phase_start = t
        elif part == "G" and want and want != axis_of(js.signal):
            hold = self.preempt_min_green if is_preempt else self.min_green
            if js.t_in >= hold:
                self._set(j, js, NEXT_SIGNAL[js.signal], t, "preempt" if is_preempt else "switch", requested=want)

    def _set(self, j, js, signal, t, reason, requested=None) -> None:
        self.events.append(SignalEvent(t, j, requested, signal, reason))
        js.signal = signal
        js.t_in = 0.0

    def _reject(self, t, j, requested, reason) -> None:
        self.rejections += 1
        self.events.append(SignalEvent(t, j, str(requested), None, "rejected", reason))

    def record(self, t: float, junction: str | None, reason: str, executed: str | None = None, detail: str = "") -> None:
        self.events.append(SignalEvent(t, junction, None, executed, reason, detail))

    # --- read-only views ------------------------------------------------
    def signals(self) -> dict[str, str]:
        return {j: js.signal for j, js in self.junctions.items()}

    def state(self, t: float) -> dict:
        return {
            "t": t,
            "junctions": {
                j: {
                    "signal": js.signal,
                    "phase": axis_of(js.signal),
                    "green": js.signal.endswith("_G"),
                    "time_in_state": js.t_in,
                    "can_switch": js.signal.endswith("_G") and js.t_in >= self.min_green,
                }
                for j, js in self.junctions.items()
            },
        }

    def min_time_to_change(self, j: str) -> float:
        """Earliest time (s) until this junction's current state can end — used by the signal-data API."""
        js = self.junctions[j]
        part = js.signal[3:]
        if part == "Y":
            return max(0.0, self.yellow - js.t_in)
        if part == "AR":
            return max(0.0, self.all_red - js.t_in)
        return max(0.0, self.min_green - js.t_in)

    def initial(self, axis: str = "EW") -> None:
        for js in self.junctions.values():
            js.signal = green_signal(axis)
            js.t_in = 0.0
