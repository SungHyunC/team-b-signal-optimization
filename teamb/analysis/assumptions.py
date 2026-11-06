"""Every number the impact & cost-benefit analysis uses, with where it comes from.

Owner: Scenarios & analysis (Aditya, with Doyoung).

Each Assumption has a `basis`:
    cited       taken from the named source (dollar year in the unit)
    derived     computed from cited numbers; the derivation is in `source`
    assumption  a team assumption — change it, and say so, when better local data exist
    model       a property of our simulation model

Override any value without editing code:  python -m teamb.analysis.impact DIR --params my.json
where my.json is {"vehicle_occupancy": 1.2, "annual_hours": {"rush_hour": 750}, ...}.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Assumption:
    name: str
    value: float
    unit: str
    basis: str  # cited | derived | assumption | model
    source: str


ASSUMPTIONS: list[Assumption] = [
    # --- value of time ------------------------------------------------------------------
    Assumption(
        "value_of_time_usd_per_person_h", 21.10, "USD (2023) per person-hour", "cited",
        "USDOT, Benefit-Cost Analysis Guidance for Discretionary Grant Programs (May 2025 update), "
        "Table A-2: value of travel time savings, general travel, all purposes.",
    ),
    Assumption(
        "truck_value_of_time_usd_per_veh_h", 35.70, "USD (2023) per truck-hour", "cited",
        "USDOT BCA Guidance (May 2025): truck drivers' value of travel time.",
    ),
    Assumption(
        "vehicle_occupancy", 1.52, "persons per car", "cited",
        "USDOT BCA Guidance (May 2025): average vehicle occupancy, passenger vehicles, all travel "
        "(as applied in NCDOT's 2025 BCA technical memorandum). Peak commuting is lower "
        "(Caltrans Cal-B/C uses 1.15 peak / 1.30 off-peak for California).",
    ),
    Assumption(
        "truck_share", 0.04, "share of vehicles", "model",
        "Truck share of the arterial through demand in teamb/demand/presets.py (rush hour).",
    ),
    # --- fuel and CO2 -----------------------------------------------------------------------
    Assumption(
        "idle_fuel_gal_per_h", 0.25, "gal per vehicle-hour of delay", "derived",
        "US DOE Vehicle Technologies Office, Fact #861 (Feb 2015): idling burns 0.16 gal/h (compact "
        "sedan, 2.0 L) to 0.39 gal/h (large sedan, 4.6 L), from Argonne's worksheet; 0.25 is a fleet-mix "
        "midpoint. Delay (SUMO timeLoss) also includes slow driving, so this is an approximation.",
    ),
    Assumption(
        "fuel_per_stop_gal", 0.005, "gal per extra stop", "derived",
        "Physics estimate: kinetic energy of a 1,500 kg car at 50 km/h (≈145 kJ) ÷ ~20 % engine and "
        "drivetrain efficiency ÷ 121 MJ per gallon (US EPA: 33.7 kWh per gallon of gasoline) ≈ 0.006 "
        "gal, rounded down.",
    ),
    Assumption(
        "fuel_price_usd_per_gal", 4.27, "USD (2023) per gallon", "cited",
        "Caltrans, 2025 INFRA Cal-B/C vs federal value comparison matrix: California regular gasoline "
        "(EIA data, 2023 dollars).",
    ),
    Assumption(
        "fuel_tax_usd_per_gal", 0.762, "USD (2023) per gallon", "cited",
        "Same Caltrans matrix: federal excise $0.183 + California excise $0.579 per gallon. Taxes are "
        "transfers, so the resource cost of fuel is price minus tax.",
    ),
    Assumption(
        "co2_kg_per_gal", 8.887, "kg CO2 per gallon of gasoline", "cited",
        "US EPA, Greenhouse Gas Emissions from a Typical Passenger Vehicle: 8,887 g CO2 per gallon.",
    ),
    Assumption(
        "co2_usd_per_tonne", 190.0, "USD (2020) per tonne CO2", "cited",
        "US EPA (2023), Report on the Social Cost of Greenhouse Gases: 2020 emissions, 2 % discount "
        "rate. Converted to 2023 dollars with cpi_2020_to_2023 before it is added to the 2023-dollar time "
        "and fuel values. Note: USDOT's May 2025 guidance no longer monetizes CO2; set 0 to follow it.",
    ),
    Assumption(
        "cpi_2020_to_2023", 1.177, "USD (2023) per USD (2020)", "cited",
        "US BLS, CPI-U (all urban consumers, US city average) annual averages: 304.702 (2023) / 258.811 "
        "(2020) = 1.177. Puts the 2020-dollar CO2 value in the dollar year of the other values.",
    ),
    # --- deployment cost ----------------------------------------------------------------------
    Assumption(
        "intersections", 4, "signalized intersections", "model",
        "The modeled corridor J1–J4.",
    ),
    Assumption(
        "adaptive_capex_per_intersection_usd", 65000, "USD per intersection", "cited",
        "Lodes & Benekohal (2013), Safety Benefits of Implementing Adaptive Signal Control Technology, "
        "Illinois Center for Transportation, FHWA-ICT-12-020: literature range $46,000–65,000 per "
        "intersection (their survey average was $38,223). The upper end is used to stay conservative.",
    ),
    Assumption(
        "adaptive_om_per_intersection_usd_per_year", 5000, "USD per intersection-year", "assumption",
        "About 8 % of capital per year for detection, communications and software support.",
    ),
    Assumption(
        "actuated_capex_per_intersection_usd", 20000, "USD per intersection", "assumption",
        "Detector repair/upgrade and actuated timing on existing controllers.",
    ),
    Assumption(
        "actuated_om_per_intersection_usd_per_year", 2000, "USD per intersection-year", "assumption",
        "Detector maintenance.",
    ),
    Assumption(
        "retiming_capex_per_intersection_usd", 4000, "USD per intersection", "assumption",
        "One-time signal retiming / coordination study (order of magnitude of agency retiming "
        "programs; verify with a local quote).",
    ),
    Assumption(
        "recommender_capex_per_intersection_usd", 5000, "USD per intersection", "assumption",
        "Data integration and engineer review for AI-recommended timing plans on existing hardware "
        "(Green Light style: software only).",
    ),
    Assumption(
        "recommender_om_per_intersection_usd_per_year", 2000, "USD per intersection-year", "assumption",
        "Engineer time to review and apply recommendations.",
    ),
    Assumption("service_life_years", 10, "years", "assumption", "Typical life of signal detection and controller equipment."),
    Assumption(
        "discount_rate", 0.07, "per year, real", "cited",
        "USDOT BCA Guidance (May 2025): 7 % real discount rate (Caltrans Cal-B/C uses 4 %).",
    ),
    # --- how the simulation maps to a year --------------------------------------------------
    Assumption(
        "unfinished_trip_delay_s", 300, "s of delay per stranded trip", "assumption",
        "Each trip that was never inserted or that teleported in the measurement window is charged SUMO's "
        "teleport threshold of delay, so a controller can never gain by stranding vehicles (PERF-01). Trips "
        "still driving at the end are charged the delay they accrued (the runs have no drain period, so most "
        "of them are ordinary in-flight traffic, not stranded); summaries without that detail charge every "
        "unfinished trip.",
    ),
    Assumption(
        "unfinished_tolerance_pp", 1.0, "percentage points", "assumption",
        "A candidate with more unfinished trips than the baseline by more than this is flagged and "
        "its benefits are not claimed in the annual total.",
    ),
    Assumption(
        "ev_trips_per_year", 1100, "emergency runs per year through the corridor", "assumption",
        "About three ambulance or fire runs a day. Multiplies the paired EV time saved in the claimed 'emergency' "
        "scenario rows (seed-weighted); PERF-01 rows and other EV scenarios (earthquake) are excluded. Emergency "
        "time saved is reported in hours, not dollars.",
    ),
]

# Hours per year that each scenario represents (all ASSUMPTIONS; the emergency and security
# scenarios overlap with rush hour, so they add no traffic hours of their own).
ANNUAL_HOURS: dict[str, float] = {
    "rush_hour": 500.0,  # 2 peak hours (AM + PM, assumed alike) x 250 weekdays
    "off_peak": 2920.0,  # 8 night hours x 365 days
    "special_event": 40.0,  # 20 events a year x 2 hours
    "road_closure": 6.0,  # e.g. 3 flood closures a year x 2 hours
    "sinkhole_cross": 4.0,  # e.g. 2 utility/sinkhole closures a year x 2 hours
    "earthquake": 1.0,  # expected hours per year of a rare, damaging event
    "emergency": 0.0,  # counted through ev_trips_per_year instead
    "fake_data_attack": 0.0,  # a security test, not an operating condition
}

# Which deployment cost applies to which controller (matched on the name; first match wins).
COST_PROFILES: list[tuple[str, str, str | None]] = [
    # (name contains, capex assumption, O&M assumption). Plain "fixed_time" is the status quo
    # and costs nothing; a fixed-time variant with new parameters ("fixed_time-1a2b3c") is a retiming.
    ("fixed_time-", "retiming_capex_per_intersection_usd", None),
    ("coordinated", "retiming_capex_per_intersection_usd", None),
    ("actuated", "actuated_capex_per_intersection_usd", "actuated_om_per_intersection_usd_per_year"),
    ("recommend", "recommender_capex_per_intersection_usd", "recommender_om_per_intersection_usd_per_year"),
    ("", "adaptive_capex_per_intersection_usd", "adaptive_om_per_intersection_usd_per_year"),  # max-pressure, RL, ...
]


@dataclass
class ImpactParams:
    """The assumption values as attributes, plus the scenario-hour table."""

    values: dict[str, float] = field(default_factory=lambda: {a.name: a.value for a in ASSUMPTIONS})
    annual_hours: dict[str, float] = field(default_factory=lambda: dict(ANNUAL_HOURS))
    overridden: set[str] = field(default_factory=set)

    def __getattr__(self, name: str) -> float:
        values = self.__dict__.get("values", {})
        if name in values:
            return values[name]
        raise AttributeError(name)

    @classmethod
    def with_overrides(cls, overrides: dict | None = None) -> "ImpactParams":
        params = cls()
        for key, value in (overrides or {}).items():
            if key == "annual_hours":
                params.annual_hours.update({k: float(v) for k, v in value.items()})
                params.overridden.add(key)
            elif key in params.values:
                params.values[key] = float(value)
                params.overridden.add(key)
            else:
                raise KeyError(f"unknown impact parameter '{key}' (known: annual_hours, {', '.join(sorted(params.values))})")
        params.validate()
        return params

    def validate(self) -> None:
        """Reject values the cost-benefit formulas cannot use (ValueError naming the parameter)."""
        v = self.values
        life = v["service_life_years"]
        if not life > 0 or life != int(life):
            # the NPV sums whole years while the capital recovery factor would use a fractional one
            raise ValueError(f"service_life_years must be a whole number of years > 0, not {life:g}")
        if not v["discount_rate"] > -1:
            raise ValueError(f"discount_rate must be > -1, not {v['discount_rate']:g}")
        if v["intersections"] < 0:
            raise ValueError(f"intersections must be >= 0, not {v['intersections']:g}")

    def cost_of(self, controller: str) -> tuple[float, float, str]:
        """(capex for the corridor, O&M per year, which profile) for a controller name."""
        n = self.values["intersections"]
        if controller == "fixed_time":
            return 0.0, 0.0, "status quo"
        for needle, capex_key, om_key in COST_PROFILES:
            if needle in controller:
                capex = self.values[capex_key] * n if capex_key else 0.0
                om = self.values[om_key] * n if om_key else 0.0
                return capex, om, capex_key or "status quo"
        return 0.0, 0.0, "status quo"
