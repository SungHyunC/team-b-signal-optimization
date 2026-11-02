"""A small statistics toolkit for paired experiments (no scipy needed).

Everything the experiment report uses:

mean_ci(values)
    mean, sample standard deviation s and the half-width of the 95 % confidence interval
        ci95 = t_{0.975, n-1} * s / sqrt(n)
    so the interval is mean ± ci95. With n = 1 the interval is undefined (None).

paired(baseline, candidate)
    Matched demand seeds: both controllers saw exactly the same vehicles (REP-01), so we
    compare them seed by seed. For every seed i present in both:
        d_i   = candidate_i - baseline_i          (seconds; negative = candidate is lower)
        imp_i = 100 * (baseline_i - candidate_i) / baseline_i   (% improvement, lower-is-better
                metrics; seeds with baseline_i <= 0 are skipped to avoid an undefined ratio)
    and we report mean ± ci95 of d and of imp (t-distribution, n-1 degrees of freedom),
    the paired t statistic t = mean(d) / (s_d / sqrt(n)) and its two-sided p-value.
    The paired design removes the seed-to-seed demand variation from the comparison, which
    is why it needs far fewer seeds than comparing two independent groups.

holm(p_values)
    Holm-Bonferroni correction when several controllers are compared with the same
    baseline: sort the m p-values, multiply the k-th smallest by (m - k + 1), make the
    sequence non-decreasing and cap at 1.

t_critical(df)
    The 97.5 % quantile of Student's t (two-sided 95 %), from the usual printed table;
    between table rows it is interpolated linearly in 1/df (standard practice).

t_sf(t, df)
    P(T > t) for Student's t, via the regularized incomplete beta function
        P(T > t) = 0.5 * I_{df/(df+t^2)}(df/2, 1/2)   for t >= 0
    (continued fraction from Numerical Recipes). Used for p-values only.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

# Two-sided 95 % critical values t_{0.975, df} (any statistics textbook table).
T_975 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
    40: 2.021, 50: 2.009, 60: 2.000, 80: 1.990, 100: 1.984, 120: 1.980,
}
Z_975 = 1.960


def t_critical(df: int) -> float:
    """Two-sided 95 % critical value of Student's t with `df` degrees of freedom."""
    if df < 1:
        raise ValueError("t_critical needs df >= 1")
    if df in T_975:
        return T_975[df]
    keys = sorted(T_975)
    if df > keys[-1]:
        lo, t_lo = keys[-1], T_975[keys[-1]]
        return Z_975 + (t_lo - Z_975) * (lo / df)  # 1/df -> 0 gives the normal value
    lo = max(k for k in keys if k < df)
    hi = min(k for k in keys if k > df)
    w = (1 / df - 1 / lo) / (1 / hi - 1 / lo)
    return T_975[lo] + w * (T_975[hi] - T_975[lo])


def _clean(values: Iterable) -> list[float]:
    out = []
    for v in values:
        if v is None:
            continue
        v = float(v)
        if math.isfinite(v):
            out.append(v)
    return out


def mean_ci(values: Iterable) -> dict:
    """{"mean", "ci95", "n", "sd"}; ci95 is the half-width of the 95 % interval."""
    xs = _clean(values)
    n = len(xs)
    if n == 0:
        return {"mean": None, "ci95": None, "n": 0, "sd": None}
    m = sum(xs) / n
    if n == 1:
        return {"mean": m, "ci95": None, "n": 1, "sd": None}
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return {"mean": m, "ci95": t_critical(n - 1) * sd / math.sqrt(n), "n": n, "sd": sd}


def improvement_pct(baseline: float | None, candidate: float | None) -> float | None:
    """100 * (baseline - candidate) / baseline for a lower-is-better metric; None if undefined."""
    if baseline is None or candidate is None or baseline <= 0:
        return None
    return 100.0 * (baseline - candidate) / baseline


def paired(baseline: Mapping, candidate: Mapping) -> dict:
    """Paired comparison over the seeds present (with a value) in both mappings seed -> value."""
    seeds = sorted(
        s for s in set(baseline) & set(candidate) if baseline[s] is not None and candidate[s] is not None
    )
    diffs = [float(candidate[s]) - float(baseline[s]) for s in seeds]
    imps = [improvement_pct(float(baseline[s]), float(candidate[s])) for s in seeds]
    d = mean_ci(diffs)
    imp = mean_ci(i for i in imps if i is not None)
    t_stat = p_value = None
    if d["n"] >= 2:
        if d["sd"] and d["sd"] > 0:
            t_stat = d["mean"] / (d["sd"] / math.sqrt(d["n"]))
            p_value = t_two_sided_p(t_stat, d["n"] - 1)
        else:  # every seed gave exactly the same difference
            t_stat = 0.0 if d["mean"] == 0 else math.copysign(math.inf, d["mean"])
            p_value = 1.0 if d["mean"] == 0 else 0.0
    mb = sum(float(baseline[s]) for s in seeds) / len(seeds) if seeds else None
    mc = sum(float(candidate[s]) for s in seeds) / len(seeds) if seeds else None
    return {
        "seeds": seeds,
        "n": len(seeds),
        "baseline_mean": mb,
        "candidate_mean": mc,
        "diff": {"mean": d["mean"], "ci95": d["ci95"]},
        "diff_sd": d["sd"],
        "improvement_pct": {"mean": imp["mean"], "ci95": imp["ci95"], "n": imp["n"]},
        "improvement_of_means_pct": improvement_pct(mb, mc),
        "t": t_stat,
        "p_value": p_value,
    }


def holm(p_values: list[float | None]) -> list[float | None]:
    """Holm-Bonferroni adjusted p-values, in the original order (None stays None)."""
    idx = [i for i, p in enumerate(p_values) if p is not None]
    m = len(idx)
    order = sorted(idx, key=lambda i: p_values[i])
    adjusted: list[float | None] = [None] * len(p_values)
    running = 0.0
    for k, i in enumerate(order):
        running = max(running, min(1.0, (m - k) * p_values[i]))
        adjusted[i] = running
    return adjusted


# --- Student's t distribution (for p-values) -------------------------------------
def _betacf(a: float, b: float, x: float, max_iter: int = 300, eps: float = 3e-14) -> float:
    """Continued fraction for the incomplete beta function (Numerical Recipes, betacf)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_bt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x)
    bt = math.exp(log_bt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_sf(t: float, df: float) -> float:
    """P(T > t) for Student's t with df degrees of freedom."""
    if math.isinf(t):
        return 0.0 if t > 0 else 1.0
    tail = 0.5 * betainc(df / 2.0, 0.5, df / (df + t * t))
    return tail if t >= 0 else 1.0 - tail


def t_two_sided_p(t: float, df: float) -> float:
    return min(1.0, 2.0 * t_sf(abs(t), df))
