"""Security checks on the data a controller is about to act on.

Owner: AI & security (Yunseong). Threat model: docs/roles/ai-security.md.

`ObservationGuard` answers three questions before a controller trusts an observation:

1. Is it fresh?    its `t` is more than `max_age_s` behind the controller's clock → "stale"
                   (frozen feed, lagging server, cut cable)
2. Is it new?      its `t` goes backwards compared with the last one we accepted → "replayed"
                   (old telemetry sent again)
3. Is a probe number believable?
     - the sensor cross-check flagged it (`probe.trusted` is False: navigation-app
       probes disagree with the loop detectors, e.g. 99 phones in a handcart), or
     - it claims more stopped cars than the approach lanes can physically hold.

What the controllers do with a "no":
    stale / replayed / missing observation → run the approved fixed-time fallback plan
    untrusted / impossible probe number    → use the loop detector for that approach

Every rejection is counted in `guard.rejected` (a Counter), so a run can report how often
the defense fired.

Tunable: `max_age_s`, `storage_margin`, `VEH_SPACING_M` (jam spacing for the storage limit).
"""
from __future__ import annotations

import math
from collections import Counter

VEH_SPACING_M = 7.0  # metres per stopped car (4.5 m car + 2.5 m gap), same as evaluation


class ObservationGuard:
    def __init__(self, topology, *, max_age_s: float = 10.0, storage_margin: float = 1.2):
        self.max_age_s = float(max_age_s)
        self.storage_margin = float(storage_margin)
        # most cars each approach can hold: lane length × lanes / jam spacing
        self.storage: dict[tuple[str, str], float] = {}
        for j, sides in topology.approach_lanes.items():
            for side, lanes in sides.items():
                metres = sum(topology.lane_length(lane) for lane in lanes)
                self.storage[(j, side)] = metres / VEH_SPACING_M
        self.last_t: float | None = None
        self.rejected: Counter = Counter()

    def check_observation(self, observation, now: float) -> str | None:
        """Return why the observation must not be used ("missing", "stale", "replayed") or None."""
        if not isinstance(observation, dict) or observation.get("t") is None:
            reason = "missing"
        elif not isinstance(observation.get("junctions"), dict):
            reason = "missing"
        else:
            t = float(observation["t"])
            if now - t > self.max_age_s:
                reason = "stale"
            elif self.last_t is not None and t < self.last_t:
                reason = "replayed"
            else:
                self.last_t = t
                return None
        self.rejected[reason] += 1
        return reason

    def probe_value(self, junction: str, side: str, entry: dict | None, key: str = "queue_est") -> float | None:
        """A probe number we are willing to act on, or None (caller falls back to the detector)."""
        probe = (entry or {}).get("probe") or {}
        return self.screen(junction, side, entry, probe.get(key))

    def screen(self, junction: str, side: str, entry: dict | None, cars: float | None) -> float | None:
        """Pass a probe-derived car count only if the cross-check trusts it and it fits on the road."""
        if cars is None:
            return None
        probe = (entry or {}).get("probe") or {}
        if probe.get("trusted") is False:
            self.rejected["untrusted_probe"] += 1
            return None
        if cars > self.storage.get((junction, side), math.inf) * self.storage_margin:
            self.rejected["implausible_probe"] += 1
            return None
        return float(cars)
