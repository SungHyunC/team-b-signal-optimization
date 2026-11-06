"""Impact & cost-benefit correctness (no SUMO): statistics, pairing, annualization, PERF-01."""
from __future__ import annotations

import pytest

from teamb.analysis import impact
from teamb.evaluation import stats


def test_summary_stat_matches_the_shared_t_interval():
    vals = list(range(40))  # df = 39: the old local table stopped at 30 and used z = 1.96
    s = impact._summary_stat(vals)
    assert s["ci95"] == pytest.approx(stats.mean_ci(vals)["ci95"])
    assert s["ci95"] > 1.96 * stats.mean_ci(vals)["sd"] / 40 ** 0.5
    assert impact._summary_stat([1.0, None, float("nan")]) == {"mean": 1.0, "ci95": None, "n": 1}
    assert impact._summary_stat([]) == {"mean": None, "ci95": None, "n": 0}
