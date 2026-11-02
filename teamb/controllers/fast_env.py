"""Faster SimEnv variants for the AI plan search and RL training (subclasses; sim/ is untouched).

Owner: AI & security (Yunseong).

Profiling a SimEnv step with the first sensor version: reading the sensors (~300 TraCI
calls) took about 85 % of the time and live KPI sampling another ~10 %; SUMO itself is
~1 ms. (The sensors now use TraCI subscriptions and are much cheaper, but the plan search
runs hundreds of simulations, so every saved millisecond still counts.) Two jobs do not
need all of that:

    PlanEvalEnv  evaluates a *fixed* timing plan: no sensor reads, live KPIs once a minute.
    TrainEnv     RL training: sensors read only on decision ticks (every `observe_every` s),
                 live KPIs once a minute. The RL controller only looks at observations on
                 those ticks, so it sees exactly what it would see in a normal SimEnv.

End-of-run metrics (delay, travel time, unfinished) come from SUMO's tripinfo file, so
they are identical to a normal run. Import this module lazily (it imports teamb.sim.env,
which imports teamb.controllers).
"""
from __future__ import annotations

from teamb.sim.env import SimEnv


class _NoSensors:
    """Stand-in for SensorSuite when a fixed plan needs no observations.

    Only `observe` is skipped; everything else (on_step bookkeeping, attacks, frames) is
    passed to the real suite.
    """

    def __init__(self, real):
        self._real = real

    def observe(self, t, source="detector"):
        return {"t": t, "coverage": 0.0, "sampling": "none", "junctions": {}, "alerts": []}

    def __getattr__(self, name):
        return getattr(self._real, name)


class _TickSensors:
    """Reads the real sensors only every `every` seconds and repeats that observation in between."""

    def __init__(self, real, every: int):
        self._real = real
        self.every = max(1, int(every))
        self._cached = None

    def observe(self, t, source="detector"):
        if self._cached is None or int(round(t)) % self.every == 0:
            self._cached = self._real.observe(t, source)
        return self._cached

    def __getattr__(self, name):
        return getattr(self._real, name)


def _skip_live_kpis(metrics, every: float = 60.0) -> None:
    """Live KPIs (queues, current delay) are for the twin; delay and travel time come from tripinfo.

    We still take a sample every `every` seconds (instead of every 5 s) so the queue
    statistics in the summary stay defined.
    """
    original = getattr(metrics, "_sample", None)
    if original is None:
        return
    next_t = [float("-inf")]

    def rarely(t):
        if t >= next_t[0]:
            next_t[0] = t + every
            original(t)

    metrics._sample = rarely


class PlanEvalEnv(SimEnv):
    def start(self):
        super().start()
        self.sensors = _NoSensors(self.sensors)
        _skip_live_kpis(self.metrics)
        return self


class TrainEnv(SimEnv):
    def __init__(self, *args, observe_every: int = 5, **kwargs):
        super().__init__(*args, **kwargs)
        self.observe_every = int(observe_every)

    def start(self):
        super().start()
        self.sensors = _TickSensors(self.sensors, self.observe_every)
        _skip_live_kpis(self.metrics)
        return self
