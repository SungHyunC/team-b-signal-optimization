"""Time-of-day demand profiles.

Owner: Scenarios & analysis (Aditya).

A profile is a tuple of (time_s, multiplier) breakpoints. The multiplier is linear between
breakpoints and constant before the first and after the last one. A Flow's rate at time t
is `veh_per_hour * multiplier(profile, t)`, so `veh_per_hour` is the PEAK rate when the
profile tops out at 1.0.

    >>> p = peak(start=900, ramp_up=900, hold=1500, ramp_down=1200, base=0.85, top=1.0, end_level=0.75)
    >>> multiplier(p, 0), multiplier(p, 1350), multiplier(p, 2500)
    (0.85, 0.925, 1.0)
"""
from __future__ import annotations

Profile = tuple[tuple[float, float], ...]


def flat(level: float = 1.0) -> Profile:
    """The same multiplier all the time."""
    return ((0.0, float(level)),)


def peak(
    *,
    start: float,
    ramp_up: float,
    hold: float,
    ramp_down: float,
    base: float,
    top: float = 1.0,
    end_level: float | None = None,
    pre: tuple[float, float] | None = None,
) -> Profile:
    """`base` until `start`, a linear rise to `top`, `hold` seconds at the top, then a linear
    fall to `end_level` (defaults to `base`). `pre=(t0, level)` adds an earlier breakpoint,
    e.g. a quieter start of the warm-up."""
    end_level = base if end_level is None else end_level
    points = [] if pre is None else [(float(pre[0]), float(pre[1]))]
    t1 = start + ramp_up
    t2 = t1 + hold
    points += [(float(start), base), (float(t1), top), (float(t2), top), (float(t2 + ramp_down), end_level)]
    return tuple(points)


def pulse(*, start: float, rise: float, hold: float, fall: float, top: float = 1.0, base: float = 0.0) -> Profile:
    """A surge: `base`, then up to `top` over `rise` s, `hold` s at the top, down over `fall` s."""
    return peak(start=start, ramp_up=rise, hold=hold, ramp_down=fall, base=base, top=top, end_level=base)


def dip(*, start: float, end: float, factor: float, ramp_in: float = 300.0, ramp_out: float = 600.0) -> Profile:
    """1.0, easing down to `factor` over `ramp_in` s after `start`, back up to 1.0 over
    `ramp_out` s after `end` — e.g. regional traffic avoiding a closed corridor."""
    return ((float(start), 1.0), (float(start + ramp_in), factor), (float(end), factor), (float(end + ramp_out), 1.0))


def _limits(profile: Profile, t: float) -> tuple[float, float]:
    """(value just before t, value just after t) — they differ where a profile jumps."""
    at = [m for tt, m in profile if tt == t]
    if at:
        return at[0], at[-1]
    m = multiplier(profile, t)
    return m, m


def combine(a: Profile | None, b: Profile | None) -> Profile | None:
    """The product of two profiles, exact at every breakpoint of either (including jumps) and
    linear in between (close enough for demand shapes)."""
    if not a:
        return b
    if not b:
        return a
    points = []
    for t in sorted({t for t, _ in a} | {t for t, _ in b}):
        (la, ra), (lb, rb) = _limits(a, t), _limits(b, t)
        left, right = round(la * lb, 6), round(ra * rb, 6)
        points.append((t, left))
        if right != left:
            points.append((t, right))
    return tuple(points)


def multiplier(profile: Profile | None, t: float) -> float:
    """Multiplier at time t (1.0 when there is no profile)."""
    if not profile:
        return 1.0
    if t <= profile[0][0]:
        return profile[0][1]
    for (t0, m0), (t1, m1) in zip(profile, profile[1:]):
        if t <= t1:
            return m0 if t1 == t0 else m0 + (m1 - m0) * (t - t0) / (t1 - t0)
    return profile[-1][1]


def max_multiplier(profile: Profile | None, t0: float, t1: float) -> float:
    """Largest multiplier on [t0, t1] (piecewise linear → it is at a breakpoint or an end)."""
    if not profile:
        return 1.0
    candidates = [multiplier(profile, t0), multiplier(profile, t1)]
    candidates += [m for t, m in profile if t0 <= t <= t1]
    return max(candidates)


def integral(profile: Profile | None, t0: float, t1: float) -> float:
    """Exact integral of the multiplier over [t0, t1] in seconds (for expected vehicle counts)."""
    if t1 <= t0:
        return 0.0
    if not profile:
        return t1 - t0
    cuts = sorted({t0, t1, *(t for t, _ in profile if t0 < t < t1)})
    # segment [a, b]: start at the value just after a, end at the value just before b (jumps)
    return sum((b - a) * (_limits(profile, a)[1] + _limits(profile, b)[0]) / 2 for a, b in zip(cuts, cuts[1:]))
