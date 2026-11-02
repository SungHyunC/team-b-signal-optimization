"""The scenario catalog: baseline demand, first-responder emergencies, natural disasters and a
security test (Aditya's scenario list + Yunseong's security test).

Owner: Scenarios & analysis (Aditya). Each scenario is a function decorated with @register
that returns a Scenario. Times are simulation seconds; the measurement window is
[warmup, duration) = [900, 4500) unless a scenario says otherwise. docs/scenarios.md
explains what each one tests and which metrics to read.
"""
from __future__ import annotations

from dataclasses import replace

from teamb.demand.presets import EVENING, OFF_PEAK, OFF_PEAK_PROFILE, RUSH_HOUR, RUSH_PROFILE
from teamb.demand.profiles import combine, dip, flat, pulse
from teamb.demand.routes import Flow
from teamb.scenarios import Event, Scenario, register

ADITYA = "Scenarios & analysis (Aditya)"
CORE_MEASURES = ["mean_delay_s", "stops_per_veh", "mean_travel_time_s", "p95_travel_time_s", "unfinished_pct"]
SPREAD_MEASURES = ["max_queue_veh", "spillback_samples", "throughput_veh_h"]


def rush_flows(scale: float = 1.0) -> list[Flow]:
    """The morning-peak corridor demand with its time-of-day profile."""
    demand = RUSH_HOUR if scale == 1.0 else RUSH_HOUR.scaled(scale)
    return demand.flows(RUSH_PROFILE)


def with_diversion(flows: list[Flow], *, start: float, end: float, share: float, names=("EB through",)) -> list[Flow]:
    """Regional traffic avoiding a closed corridor: the named flows lose `share` of their
    vehicles between `start` and `end` (easing in over 5 min once navigation apps show the
    closure, back over 10 min after it reopens). share=0 turns this off (a pure stress test)."""
    if share <= 0:
        return flows
    shape = dip(start=start, end=end, factor=1.0 - share)
    return [replace(f, profile=combine(f.profile, shape)) if f.name in names else f for f in flows]


CLOSURE_DIVERSION = 0.3  # ASSUMPTION: 30 % of eastbound through trips take another corridor during the flood


def ev(time: float, origin: str, destination: str, kind: str = "ambulance") -> Event:
    return Event(time, "dispatch_ev", {"origin": origin, "destination": destination, "kind": kind})


# --- baseline & demand ----------------------------------------------------------
@register
def rush_hour() -> Scenario:
    return Scenario(
        name="rush_hour",
        title="Baseline · Rush hour",
        title_ko="기본 · 출퇴근 혼잡",
        description=(
            "Morning peak toward downtown: heavy eastbound arterial traffic that ramps up, peaks for "
            "25 minutes and eases off, lighter westbound, and cross streets of different sizes. Fixed-time "
            "control builds real queues here; adaptive control has room to win."
        ),
        flows=rush_flows(),
        category="baseline",
        question="How much delay, stopping and queueing does each controller cause in normal peak traffic?",
        measures=CORE_MEASURES + SPREAD_MEASURES,
        owner=ADITYA,
    )


@register
def off_peak() -> Scenario:
    return Scenario(
        name="off_peak",
        title="Night · Light traffic",
        title_ko="야간 · 한산한 교통",
        description=(
            "Light, balanced night traffic with more trucks. A fixed 90 s cycle makes drivers wait at "
            "empty junctions; detector-actuated control should cut delay and stops the most."
        ),
        flows=OFF_PEAK.flows(OFF_PEAK_PROFILE),
        category="demand",
        question="Does the controller stop wasting green time when the roads are nearly empty?",
        measures=["mean_delay_s", "stops_per_veh", "mean_travel_time_s"],
        owner=ADITYA,
    )


@register
def special_event() -> Scenario:
    # The stadium's garage exits onto the cross street between N3 and J3, so every car leaving
    # it must clear J3's north approach (from NN3 SUMO would spread them over the back street).
    stadium = pulse(start=1500, rise=300, hold=1200, fall=600)  # the crowd leaves over 35 minutes
    surge = [
        Flow("N3_J3", "J3_S3", 240, name="Stadium → south (S3)", profile=stadium),
        Flow("N3_J3", "J1_W0", 240, name="Stadium → west (right at J3)", profile=stadium),
        Flow("N3_J3", "J4_E5", 200, name="Stadium → east (left at J3)", profile=stadium),
    ]
    return Scenario(
        name="special_event",
        title="Special event · Stadium lets out",
        title_ko="대형 행사 · 경기 종료 후 퇴장",
        description=(
            "Evening traffic, then the stadium garage north of J3 empties: about 680 extra veh/h leave "
            "onto the one-lane cross street into J3 for half an hour (cars wait in the garage when the "
            "street is full). A good controller gives J3's north–south phase more green without "
            "starving the arterial."
        ),
        flows=EVENING.flows(flat(1.0)) + surge,
        category="demand",
        question="Can the signals absorb a sudden surge on one cross street, and how far does its queue reach?",
        measures=["mean_delay_s", "max_queue_veh", "spillback_samples", "p95_travel_time_s", "unfinished_pct"],
        owner=ADITYA,
    )


# --- first responders -----------------------------------------------------------
@register
def emergency() -> Scenario:
    return Scenario(
        name="emergency",
        title="Emergency vehicle priority",
        title_ko="응급차량 우선 신호",
        description=(
            "Ten ambulances and fire trucks cross the corridor during rush hour from every side: both "
            "ways along the arterial, along each cross street, and with turns. Signals give them a green "
            "path; we measure their travel time and the extra delay for everyone else."
        ),
        flows=rush_flows(),
        events=[
            ev(1200, "W0_J1", "J4_E5", "ambulance"),  # eastbound, whole arterial
            ev(1500, "E5_J4", "J1_W0", "firetruck"),  # westbound, whole arterial
            ev(1800, "NN2_N2", "J2_S2", "ambulance"),  # southbound cross street at J2
            ev(2100, "S3_J3", "N3_NN3", "firetruck"),  # northbound cross street at J3
            ev(2400, "S1_J1", "J4_E5", "ambulance"),  # north, then right onto the arterial (4 signals)
            ev(2700, "NN4_N4", "J1_W0", "firetruck"),  # south, then right onto the arterial (4 signals)
            ev(3000, "W0_J1", "J3_S3", "ambulance"),  # eastbound, right turn at J3
            ev(3300, "E5_J4", "J2_S2", "firetruck"),  # westbound, left turn at J2 across eastbound traffic
            ev(3600, "S4_J4", "J1_W0", "ambulance"),  # north, then left onto the arterial
            ev(3900, "W0_J1", "J4_E5", "firetruck"),  # eastbound again, at the end of the peak
        ],
        category="emergency",
        question="How many seconds does signal preemption save an emergency vehicle, and what does it cost other traffic?",
        measures=["ev_mean_travel_time_s", "ev_count", "preemptions", "mean_delay_s", "p95_travel_time_s"],
        owner=ADITYA,
    )


# --- natural disasters ----------------------------------------------------------
@register
def road_closure() -> Scenario:
    return Scenario(
        name="road_closure",
        title="Disaster road closure (flood)",
        title_ko="재난 도로 폐쇄 (침수)",
        description=(
            "A flash flood closes the eastbound arterial between J2 and J3 for 30 minutes of the peak. "
            "Traffic detours over the back street (J2 → N2 → N3 → J3, or earlier via N1); navigation-app "
            "users re-route on live travel times and 30 % of the regional eastbound through traffic avoids "
            "the corridor. We measure how far and how long congestion spreads and how fast it recovers."
        ),
        flows=with_diversion(rush_flows(), start=1500, end=3300, share=CLOSURE_DIVERSION),
        events=[
            Event(1500, "close_road", {"edge": "J2_J3", "cause": "flood"}),
            Event(3300, "reopen_road", {"edge": "J2_J3"}),
        ],
        duration=5400,  # 35 min after reopening, so the recovery can be measured
        category="disaster",
        question="How far and how long does congestion spread when the arterial floods, and how fast does it recover?",
        measures=["unfinished_pct", "mean_delay_s", "max_queue_veh", "spillback_samples", "throughput_veh_h"],
        owner=ADITYA,
    )


@register
def sinkhole_cross() -> Scenario:
    return Scenario(
        name="sinkhole_cross",
        title="Sinkhole on a cross street",
        title_ko="교차로 이면도로 싱크홀",
        description=(
            "A sinkhole closes the cross street north of J2 (J2 ↔ N2, both directions) for 30 minutes. "
            "North–south traffic at J2 detours through J1 or J3 and the back street, adding turning traffic "
            "at the neighbouring junctions — a test of spillover between intersections."
        ),
        flows=rush_flows(),
        events=[
            Event(1500, "close_road", {"edge": "J2_N2", "cause": "sinkhole", "both_directions": True}),
            Event(3300, "reopen_road", {"edge": "J2_N2", "both_directions": True}),
        ],
        category="disaster",
        question="When one cross street is cut, does the extra turning traffic spill over to the neighbouring junctions?",
        measures=["mean_delay_s", "max_queue_veh", "spillback_samples", "unfinished_pct"],
        owner=ADITYA,
    )


@register
def earthquake() -> Scenario:
    return Scenario(
        name="earthquake",
        title="Earthquake · closures and emergency response",
        title_ko="지진 · 다중 도로 통제와 긴급 출동",
        description=(
            "An earthquake at t = 1200 s damages the J3–J4 bridge (closed both ways until inspected at "
            "3000 s) and drops debris on the cross street north of J1 (closed until 3600 s). Seven "
            "ambulances and fire trucks are dispatched from all sides and must find open routes, while "
            "lighter-than-peak traffic detours over the back street."
        ),
        flows=rush_flows(scale=0.75),
        events=[
            Event(1200, "close_road", {"edge": "J3_J4", "cause": "earthquake: bridge damage", "both_directions": True}),
            Event(1200, "close_road", {"edge": "J1_N1", "cause": "earthquake: debris", "both_directions": True}),
            ev(1230, "E5_J4", "J2_S2", "firetruck"),
            ev(1290, "W0_J1", "J4_E5", "ambulance"),
            ev(1500, "NN2_N2", "J3_S3", "ambulance"),
            ev(1800, "S4_J4", "N1_NN1", "firetruck"),
            ev(2100, "S1_J1", "J4_E5", "ambulance"),
            ev(2700, "NN4_N4", "J1_W0", "firetruck"),
            Event(3000, "reopen_road", {"edge": "J3_J4", "both_directions": True}),
            ev(3300, "E5_J4", "J1_W0", "ambulance"),
            Event(3600, "reopen_road", {"edge": "J1_N1", "both_directions": True}),
        ],
        category="disaster",
        question="With several roads cut at once, do emergency vehicles still get through fast, and does the network recover?",
        measures=["ev_mean_travel_time_s", "unfinished_pct", "mean_delay_s", "throughput_veh_h", "spillback_samples"],
        owner=ADITYA,
    )


# --- security ---------------------------------------------------------------------
@register
def fake_data_attack() -> Scenario:
    return Scenario(
        name="fake_data_attack",
        title="Security test · fake navigation data",
        title_ko="보안 테스트 · 가짜 내비 데이터",
        description=(
            "Like the 2020 Berlin case (99 phones in a handcart faked a jam on Google Maps), phantom "
            "probe reports claim a long queue on J2's north approach during the peak. Does a probe-based "
            "controller get fooled, and does the cross-check against loop detectors catch it?"
        ),
        flows=rush_flows(),
        events=[
            Event(1500, "start_attack", {"junction": "J2", "approach": "N", "n": 99}),
            Event(3300, "stop_attack", {}),
        ],
        category="security",
        question="Does fake probe data make a controller waste green time, and is it detected?",
        measures=["mean_delay_s", "stops_per_veh", "rejected_actions", "unfinished_pct"],
        owner="AI & security (Yunseong)",
        defaults={"coverage": 0.25},
    )
