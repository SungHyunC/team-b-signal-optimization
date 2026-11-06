"""Sensors: infrastructure detectors and navigation-app probe vehicles.

Owner: Data & evaluation (Doyoung). The env only uses ``SensorSuite`` with the methods
``set_coverage, on_step, is_probe, observe, inject_fake_reports, clear_fake_reports,
phantom_positions, alerts``.

Modules
-------
feed.py        one shared set of TraCI subscriptions per run (fast: no round trips per step)
sampling.py    who is a probe (uniform / approach_biased / speed_biased) and when it reports
crosscheck.py  fake-data defense: probe reports vs loop detectors (`trusted`, alerts)
logs.py        rolling counts, estimation log and detector-interval tables (evaluation only)
suite.py       SensorSuite: builds the observation every simulated second

Observation contract (what controllers receive every step)::

    {
      "t": 123.0, "coverage": 0.25, "sampling": "uniform",
      "junctions": {
        "J1": {
          "approaches": {
            "W": {
              "detector": {"queue": 4, "count": 7, "occupancy": 12.5, "speed": 3.1,
                           "flow_vph": 820.0,   # E1 loop counts over the last 5 min
                           "gap_s": 2.4},       # seconds since a loop last saw a vehicle (actuated)
              "probe":    {"queue_est": 8.0,    # halted probe reports / coverage
                           "n": 2,              # probe reports this second (incl. fake ones)
                           "halted": 2,         # of which halted (< 0.1 m/s)
                           "speed": 0.4,        # mean reported speed, m/s (None if no report)
                           "flow_est_vph": 760.0,  # probes that crossed the stop line / coverage
                           "trusted": True,     # False: reports disagree with the loop detectors
                           "queue_est_adj": 7.1,     # halted reports / estimated penetration
                           "penetration_est": 0.28,  # probe crossings / loop counts (last 15 min)
                           "n_est": 8.0},            # reports scaled to all cars (like queue_est)
              "fused":    {"queue": 4, "flow_vph": 820.0, "source": "detector"},
              "oracle":   {"queue": 5, "count": 8}   # ONLY if controller.observation_source == "oracle"
            }, ...
          },
          "exits": {"E": {"edge": "J1_J2", "detector": {...} | None}, ...}   # downstream (max-pressure)
        }, ...
      },
      "alerts": [{"type": "probe_detector_mismatch", "junction": "J2", "approach": "N",
                  "probe_queue": 396.0, "detector_queue": 2, "probe_halted": 99,
                  "test": "storage", "since": 1503.0}]
    }

Notes for controller authors
- ``queue_est``, ``flow_est_vph`` and ``n_est`` are scaled by 1/coverage, so low coverage gives
  noisy and, with biased sampling, biased numbers. Each probe counts with the coverage that was
  in effect when it departed, so the numbers stay right after the coverage changes mid-run
  (``observation["coverage"]`` is the current setting; prefer ``n_est`` over ``n / coverage``). ``queue_est_adj`` divides by the *measured* share of
  probes on that approach instead (fixes approach bias, not stopped-phone bias).
- ``penetration_est`` is kept within [c/2, 2c] of the coverage c (within [c/b, bc] with
  b = max(r, 1/r) for approach_biased:r with r > 2 or r < 1/2): right after a closure the
  first vehicles back on an approach are not a random sample, and an estimate of a few
  percent made genuine reports look fake.
- The E2 detector only sees the last 100 m. ``fused.queue`` uses the detector and, only when
  the detector zone is full and the probes are trusted, adds the halted probes reported
  upstream of the zone (scaled by the penetration), never past what fits on the approach.
  Reports claiming the zone itself (where phantom phones stand) cannot inflate it.
- ``trusted: False`` means the cross-check flagged the probe data (see crosscheck.py). While
  the detector zone is full the cross-check still compares the reports that claim the zone
  with the detector, so 20 phantom phones on a busy two-lane approach are flagged; phones
  claiming positions upstream of the zone are only bounded by the road's storage there.
- Ground truth (``oracle``) is never given to a controller unless it is explicitly an oracle
  benchmark. The evaluation logs (ground truth vs estimates) stay inside the sensors.

Sampling mechanisms (``sampling=`` of SimEnv): ``uniform``, ``approach_biased[:ratio]``,
``speed_biased[:p_report_when_stopped]``; see sampling.py.
"""
from __future__ import annotations

from teamb.sensors.feed import TrafficFeed, get_feed  # noqa: F401
from teamb.sensors.sampling import MECHANISMS, SamplingSpec, parse_sampling  # noqa: F401
from teamb.sensors.suite import PHANTOM_SPACING_M, SensorSuite  # noqa: F401

__all__ = ["SensorSuite", "TrafficFeed", "get_feed", "MECHANISMS", "SamplingSpec", "parse_sampling", "PHANTOM_SPACING_M"]
