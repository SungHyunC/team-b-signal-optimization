"""Emergency, closure and security scenarios (Aditya's ideas + Yunseong's security test).

Owner: Scenarios & analysis (Aditya). Baseline versions; tune demand and event timing here.
"""
from __future__ import annotations

from teamb.scenarios import Event, Scenario, corridor_flows, register


@register
def emergency() -> Scenario:
    return Scenario(
        name="emergency",
        title="Emergency vehicle priority",
        title_ko="응급차량 우선 신호",
        description=(
            "Ambulances and fire trucks cross the corridor during rush hour. Signals give them a green "
            "path; we measure their arrival time and the extra delay for everyone else."
        ),
        flows=corridor_flows(eb=1000, wb=550, cross=130, turn=45),
        events=[
            Event(1200, "dispatch_ev", {"origin": "W0_J1", "destination": "J4_E5", "kind": "ambulance"}),
            Event(1800, "dispatch_ev", {"origin": "S2_J2", "destination": "N2_NN2", "kind": "firetruck"}),
            Event(2400, "dispatch_ev", {"origin": "E5_J4", "destination": "J1_W0", "kind": "ambulance"}),
            Event(3000, "dispatch_ev", {"origin": "W0_J1", "destination": "J3_S3", "kind": "firetruck"}),
            Event(3600, "dispatch_ev", {"origin": "S4_J4", "destination": "J1_W0", "kind": "ambulance"}),
        ],
        owner="Scenarios & analysis (Aditya)",
    )


@register
def road_closure() -> Scenario:
    return Scenario(
        name="road_closure",
        title="Disaster road closure (flood / sinkhole)",
        title_ko="재난 도로 폐쇄 (침수·싱크홀)",
        description=(
            "A flood closes the eastbound arterial between J2 and J3. Traffic detours over the back "
            "street; we measure how far and how long congestion spreads and how fast it recovers."
        ),
        flows=corridor_flows(eb=1000, wb=550, cross=130, turn=45),
        events=[
            Event(1500, "close_road", {"edge": "J2_J3", "cause": "flood"}),
            Event(3300, "reopen_road", {"edge": "J2_J3"}),
        ],
        owner="Scenarios & analysis (Aditya)",
    )


@register
def fake_data_attack() -> Scenario:
    return Scenario(
        name="fake_data_attack",
        title="Security test · fake navigation data",
        title_ko="보안 테스트 · 가짜 내비 데이터",
        description=(
            "Like the 2020 Berlin case (99 phones in a handcart faked a jam on Google Maps), phantom "
            "probe reports claim a long queue on J2's north approach. Does a probe-based controller "
            "get fooled, and does the cross-check against loop detectors catch it?"
        ),
        flows=corridor_flows(eb=1100, wb=550, cross=130, turn=45),
        events=[
            Event(1500, "start_attack", {"junction": "J2", "approach": "N", "n": 99}),
            Event(3300, "stop_attack", {}),
        ],
        owner="AI & security (Yunseong)",
        defaults={"coverage": 0.25},
    )
