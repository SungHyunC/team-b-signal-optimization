"""Recovery after a disruption (road closure, fake-data attack): how long until traffic is normal again?

Indicator - the network *delay rate*
    r(t) = [ sum over vehicles in the network of time loss at t
             - the same vehicles' time loss at the previous sample ] / sample interval
in seconds of delay per second, i.e. "how many vehicles' worth of time the network is
losing right now" (SUMO's time loss grows by 1 s per second for a stopped car and by
1 - v/v_max for a slow one). It is sampled every 5 s by MetricsCollector (timeseries.csv).

Definition (all parameters below are arguments with these defaults)
    1. smooth r(t) with a centered moving average over one signal cycle (90 s), so the
       red/green rhythm does not look like congestion appearing and disappearing;
    2. pre-event level  L_pre  = mean of r over the 10 minutes before the event starts
       (only samples after the first 5 minutes of the run);
    3. "normal" means  r_s(t) <= L_pre * (1 + 10 %) + 1 veh  (the +1 keeps a near-empty
       network from needing an exact match);
    4. recovered at the first time t_rec >= event end from which r_s stays normal for
       2 minutes;  recovery time = t_rec - event end  (0 if it never left normal);
    5. if that never happens before the run ends the result is *censored*: we only know
       recovery took longer than (run end - event end), and report recovery_s = None.
    Excess delay = integral over [event start, t_rec (or run end)] of max(0, r(t) - L_pre) dt,
    in vehicle-hours: the extra delay the disruption caused, a single number to compare
    controllers on.

Overlapping disruptions (e.g. two closures that start together and reopen at different
times) are one disruption: `event_windows` merges overlapping or touching windows into their
union, because every window is scored against the same network-wide delay rate and separate
windows would count the same excess delay twice. Recovery is measured from the union's end.
Separate disruptions whose recovery periods still overlap (one never recovers before the next
starts) are totalled with `union_excess`, which counts each second once.

Limitation and the better reference: the scenarios use time-of-day demand profiles, so the
demand after an event can be higher than before it and the pre-event level may never come back
even when the network is fine (censored). `recovery_vs_reference` compares with a
counterfactual run instead (same seed and controller, no event); the experiment runner makes
those with `--counterfactual`.
"""
from __future__ import annotations

PRE_WINDOW_S = 600.0
SMOOTH_S = 90.0
TOLERANCE = 0.10
ABS_TOLERANCE = 1.0
HOLD_S = 120.0
IGNORE_FIRST_S = 300.0


def centered_mean(times: list[float], values: list[float], window_s: float) -> list[float]:
    """Moving average over [t - window/2, t + window/2] for every sample (two pointers, O(n))."""
    n = len(times)
    out = [0.0] * n
    half = window_s / 2.0
    lo = hi = 0
    total = 0.0
    for i, t in enumerate(times):
        while hi < n and times[hi] <= t + half:
            total += values[hi]
            hi += 1
        while lo < hi and times[lo] < t - half:
            total -= values[lo]
            lo += 1
        out[i] = total / max(1, hi - lo)
    return out


def recovery_time(
    times: list[float],
    values: list[float],
    *,
    start: float,
    end: float | None,
    pre_window_s: float = PRE_WINDOW_S,
    smooth_s: float = SMOOTH_S,
    tolerance: float = TOLERANCE,
    abs_tolerance: float = ABS_TOLERANCE,
    hold_s: float = HOLD_S,
    ignore_first_s: float = IGNORE_FIRST_S,
) -> dict:
    """Recovery of the indicator `values(times)` after an event [start, end]. See module docstring."""
    out = {
        "start": start,
        "end": end,
        "pre_level": None,
        "peak_level": None,
        "threshold": None,
        "recovered_at": None,
        "recovery_s": None,
        "censored": True,
        "excess_veh_h": None,
    }
    if not times:
        return out
    smooth = centered_mean(times, values, smooth_s)
    # raw values: a 10-min mean already spans ~7 signal cycles, and smoothed values just before
    # the start would already contain the event
    pre = [v for t, v in zip(times, values) if start - pre_window_s <= t < start and t >= ignore_first_s]
    if not pre:
        return out
    pre_level = sum(pre) / len(pre)
    threshold = pre_level * (1.0 + tolerance) + abs_tolerance
    out.update(pre_level=round(pre_level, 3), threshold=round(threshold, 3))

    recovered_at = None
    if end is not None:
        candidate = None
        for t, v in zip(times, smooth):
            if t < end:
                continue
            if v <= threshold:
                if candidate is None:
                    candidate = t
                if t - candidate >= hold_s:
                    recovered_at = candidate
                    break
            else:
                candidate = None
    stop = recovered_at if recovered_at is not None else times[-1]
    during = [(t, v, s) for t, v, s in zip(times, values, smooth) if start <= t <= stop]
    if during:
        out["peak_level"] = round(max(s for _, _, s in during), 3)
        excess = 0.0
        for k in range(1, len(during)):
            dt = during[k][0] - during[k - 1][0]
            excess += max(0.0, during[k][1] - pre_level) * dt
        out["excess_veh_h"] = round(excess / 3600.0, 3)
    if recovered_at is not None:
        out.update(recovered_at=recovered_at, recovery_s=round(recovered_at - end, 1), censored=False)
    return out


def recovery_vs_reference(
    times: list[float],
    values: list[float],
    ref_times: list[float],
    ref_values: list[float],
    *,
    start: float,
    end: float | None,
    smooth_s: float = SMOOTH_S,
    tolerance: float = TOLERANCE,
    abs_tolerance: float = ABS_TOLERANCE,
    hold_s: float = HOLD_S,
) -> dict:
    """Recovery against a counterfactual run: same seed and controller, the disruption removed.

    Demand changes during a run (time-of-day profiles), so "back to the pre-event level" can be
    unreachable even when traffic is fine. The counterfactual answers the real question - is the
    network back to where it would have been without the event? With r_s and ref_s the smoothed
    delay rates of the two runs at the same clock time:
        normal at t  <=>  r_s(t) <= ref_s(t) * (1 + 10 %) + 1 veh
        recovered at the first t >= event end from which that holds for 2 min
        excess delay = integral of max(0, r(t) - ref(t)) dt from event start to recovery (or run end)
    Both runs sample at the same times (every 5 s from t = 1 s); unmatched times are skipped."""
    out = {"start": start, "end": end, "recovered_at": None, "recovery_s": None, "censored": True, "excess_veh_h": None}
    ref = dict(zip(ref_times, centered_mean(ref_times, ref_values, smooth_s)))
    ref_raw = dict(zip(ref_times, ref_values))
    smooth = centered_mean(times, values, smooth_s)
    pairs = [(t, v, s) for t, v, s in zip(times, values, smooth) if t in ref]
    if not pairs:
        return out
    recovered_at = None
    if end is not None:
        candidate = None
        for t, _, s in pairs:
            if t < end:
                continue
            if s <= ref[t] * (1.0 + tolerance) + abs_tolerance:
                if candidate is None:
                    candidate = t
                if t - candidate >= hold_s:
                    recovered_at = candidate
                    break
            else:
                candidate = None
    stop = recovered_at if recovered_at is not None else pairs[-1][0]
    during = [(t, v) for t, v, _ in pairs if start <= t <= stop]
    if during:  # no matched samples in the window (e.g. a shorter twin run): unknown, not 0
        excess = sum(max(0.0, during[k][1] - ref_raw[during[k][0]]) * (during[k][0] - during[k - 1][0]) for k in range(1, len(during)))
        out["excess_veh_h"] = round(excess / 3600.0, 3)
    if recovered_at is not None:
        out.update(recovered_at=recovered_at, recovery_s=round(recovered_at - end, 1), censored=False)
    return out


def union_excess(times: list[float], values: list[float], spans: list[tuple]) -> float | None:
    """Excess delay (veh·h) of several windows together, each second counted once.

    spans = [(start, stop, level)]: a window integrates over [start, stop] against `level`, either
    a pre-event level (float) or a reference series {t: value} (the counterfactual run). For every
    sample interval (t[k-1], t[k]] inside at least one window, the largest excess
    max(0, values[k] - level) among those windows is counted, times the interval length. With one
    window this is that window's excess (same discretization as `recovery_time` and
    `recovery_vs_reference`); summing per-window excesses would count overlapping seconds twice.
    None if no interval lies inside a window."""
    total, counted = 0.0, False
    for k in range(1, len(times)):
        a, b = times[k - 1], times[k]
        best = None
        for start, stop, level in spans:
            if level is None or stop is None or not (start <= a and b <= stop):
                continue
            if isinstance(level, dict):
                if a not in level or b not in level:
                    continue
                level_b = level[b]
            else:
                level_b = level
            e = max(0.0, values[k] - level_b)
            best = e if best is None else max(best, e)
        if best is not None:
            total += best * (b - a)
            counted = True
    return round(total / 3600.0, 3) if counted else None


def merge_windows(windows: list[dict]) -> list[dict]:
    """Union of overlapping or touching windows ({"kind", "what", "start", "end"}; end None = still
    active at the run end). The merged window keeps start = min, end = max, the causes joined
    with '+' in "what", kind "mixed" if the kinds differ, and the original windows in "parts"
    (detail only; never summed)."""
    inf = float("inf")
    merged: list[dict] = []
    for w in sorted(windows, key=lambda w: (w["start"], str(w["what"]))):
        end = inf if w.get("end") is None else w["end"]
        part = {k: w.get(k) for k in ("kind", "what", "start", "end")}
        cur = merged[-1] if merged else None
        if cur is not None and w["start"] <= cur["_end"]:
            cur["_end"] = max(cur["_end"], end)
            for what in str(w["what"]).split("+"):
                if what not in cur["what"].split("+"):
                    cur["what"] += f"+{what}"
            if cur["kind"] != w["kind"]:
                cur["kind"] = "mixed"
            cur["parts"] += w.get("parts") or [part]
        else:
            merged.append({**w, "what": str(w["what"]), "_end": end, "parts": list(w.get("parts") or [part])})
    for cur in merged:
        end = cur.pop("_end")
        cur["end"] = None if end == inf else end
    return merged


def event_windows(events: list[dict], run_end: float | None) -> list[dict]:
    """Pair start/stop events into windows: closures (per edge) and attacks (per approach), then
    merge overlapping or touching windows into one disruption (see `merge_windows`).

    Accepts the env's event log (`SimEnv.events`) or the feed's own event list; both use
    {"t", "type", ...} with types road_closed / road_reopened / attack_started / attack_stopped."""
    windows: list[dict] = []
    open_: dict[tuple, dict] = {}
    for e in sorted(events, key=lambda e: e.get("t", 0.0)):
        kind = e.get("type")
        if kind == "road_closed":
            key = ("closure", e.get("edge"))
            if key not in open_:
                open_[key] = {"kind": "closure", "what": e.get("edge"), "start": e["t"], "end": None}
        elif kind == "road_reopened":
            w = open_.pop(("closure", e.get("edge")), None)
            if w:
                w["end"] = e["t"]
                windows.append(w)
        elif kind == "attack_started":
            key = ("attack", f"{e.get('junction')}.{e.get('approach')}")
            if key not in open_:
                open_[key] = {"kind": "attack", "what": key[1], "start": e["t"], "end": None}
        elif kind == "attack_stopped":
            target = f"{e.get('junction')}.{e.get('approach')}" if e.get("junction") else None
            for key in [k for k in open_ if k[0] == "attack" and (target is None or k[1] == target)]:
                w = open_.pop(key)
                w["end"] = e["t"]
                windows.append(w)
    windows.extend(open_.values())  # still active when the run ended
    # one disruption that closed several edges (both directions, or two closures that overlap in
    # time) is one window: scoring each against the network delay rate would double-count
    return merge_windows(windows)
