"""SimEnv — one SUMO run: scenario demand + a controller behind the safety supervisor.

Every simulation step (Aditya's controller interface):

    observation = sensors.observe(t, controller.observation_source)
    controller.observe(observation)
    action  = controller.propose_action(state)     # errors / time-outs → fixed-time fallback (SIG-02)
    safe    = supervisor.validate(action)          # malformed parts are rejected and logged
    signals = supervisor.apply_safe_action(safe, preempt=<emergency vehicles>)
    SUMO step → sensors, metrics, scenario events, controller.log(step)

Headless experiments call `SimEnv(...).run()`. The twin server steps it itself with
frames=True, which subscribes to vehicle positions for drawing.
"""
from __future__ import annotations

import csv
import itertools
import json
import subprocess
import time
import uuid
from dataclasses import asdict
from pathlib import Path

import traci
import traci.constants as tc

from teamb import config
from teamb.controllers import make_controller
from teamb.evaluation.metrics import EV_TYPES, MetricsCollector
from teamb.network.build import ensure_network, file_hash
from teamb.network.topology import load_topology
from teamb.safety.supervisor import SafetySupervisor
from teamb.scenarios import get_scenario
from teamb.scenarios.events import EVENT_KINDS, ScenarioRuntime
from teamb.sensors import SensorSuite
from teamb.sim.phases import approach_colors, axis_of, build_state, is_conflict_free
from teamb.sumo_paths import binary

_labels = itertools.count()
VEHICLE_VARS = (tc.VAR_POSITION, tc.VAR_ANGLE, tc.VAR_SPEED, tc.VAR_TYPE)
DRAWN_TYPES = ("ambulance", "firetruck", "truck", "bus")


def _git_revision() -> str:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=config.ROOT, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=config.ROOT, capture_output=True, text=True).stdout.strip()
        return (rev or "unknown") + ("-dirty" if dirty else "")
    except OSError:
        return "unknown"


class SimEnv:
    def __init__(
        self,
        scenario="rush_hour",
        controller="fixed_time",
        *,
        seed: int = 0,
        coverage: float | None = None,
        sampling: str = "uniform",
        ev_preemption: bool = True,
        controller_params: dict | None = None,
        scenario_params: dict | None = None,
        step_length: float = config.STEP_LENGTH,
        end_time: float | None = None,
        output_dir: str | Path | None = None,
        frames: bool = False,
        fallback: str = "fixed_time",
    ):
        self.scenario = get_scenario(scenario, **(scenario_params or {})) if isinstance(scenario, str) else scenario
        self.controller = (
            make_controller(controller, **(controller_params or {})) if isinstance(controller, str) else controller
        )
        self.fallback = make_controller(fallback)
        self.seed = int(seed)
        self.coverage = float(coverage if coverage is not None else self.scenario.defaults.get("coverage", 1.0))
        self.sampling = sampling
        self.ev_preemption = ev_preemption
        self.step_length = float(step_length)
        self.end_time = float(end_time if end_time is not None else self.scenario.duration)
        self.frames = frames
        self.run_id = (
            f"{self.scenario.name}__{self.controller.name}__s{self.seed}__c{round(self.coverage * 100)}__{self.sampling}__{uuid.uuid4().hex[:6]}"
        )
        self.output_dir = Path(output_dir) if output_dir else config.RESULTS / "runs" / self.run_id
        self.label = f"teamb{next(_labels)}_{uuid.uuid4().hex[:6]}"
        self.conn = None
        self.t = 0.0
        self.step_count = 0
        self.extra_in_window = 0  # vehicles added during the run (e.g. ambulances) inside the window
        self.controller_errors = 0
        self.fallback_steps = 0
        self.preemptions: list[dict] = []
        self.events: list[dict] = []
        self._event_cursor = 0
        self._shown: dict[str, str] = {}
        self._ev_ids: set[str] = set()
        self._ev_active: set[tuple[str, str]] = set()
        self._sumo_version = "unknown"
        self.summary: dict | None = None

    # --- lifecycle --------------------------------------------------------
    def start(self) -> "SimEnv":
        self._net_paths = ensure_network()
        self.topology = load_topology()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.routes_path = self.scenario.build_routes(self.output_dir / "routes.rou.xml", self.seed)
        self.tripinfo_path = self.output_dir / "tripinfo.xml"
        cmd = [
            binary("sumo"),
            "-n", str(self._net_paths.net),
            "-r", str(self.routes_path),
            "-a", str(self._net_paths.detectors),
            "--step-length", str(self.step_length),
            "--seed", str(self.seed),
            "--begin", "0",
            "--no-step-log", "true",
            "--no-warnings", "true",
            "--duration-log.disable", "true",
            "--time-to-teleport", "300",
            "--tripinfo-output", str(self.tripinfo_path),
            "--tripinfo-output.write-unfinished", "true",
        ]
        version = traci.start(cmd, label=self.label)
        if isinstance(version, tuple) and len(version) > 1:
            self._sumo_version = str(version[1])
        self.conn = traci.getConnection(self.label)
        self.supervisor = SafetySupervisor(list(self.topology.tls_ids))
        self.sensors = SensorSuite(self.conn, self.topology, coverage=self.coverage, sampling=self.sampling, seed=self.seed)
        self.metrics = MetricsCollector(self.conn, self.topology, warmup=self.scenario.warmup, end_time=self.end_time)
        cfg = self.run_config()
        self.controller.reset(cfg, self.seed, self.topology)
        self.fallback.reset(cfg, self.seed, self.topology)
        self.runtime = ScenarioRuntime(self, self.scenario)
        self._apply(self.supervisor.signals())
        self.t = self.conn.simulation.getTime()
        self._wall0 = time.time()
        self.log_event("started", scenario=self.scenario.name, controller=self.controller.name, seed=self.seed, coverage=self.coverage)
        return self

    def run(self, callback=None) -> dict:
        if self.conn is None:
            self.start()
        try:
            while self.t < self.end_time:
                self.step()
                if callback:
                    callback(self)
        except BaseException:
            self.close()
            raise
        return self.close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()

    @property
    def finished(self) -> bool:
        return self.t >= self.end_time

    def run_config(self) -> dict:
        return {
            "scenario": self.scenario.name,
            "controller": self.controller.name,
            "controller_params": self.controller.params,
            "seed": self.seed,
            "coverage": self.coverage,
            "sampling": self.sampling,
            "ev_preemption": self.ev_preemption,
            "step_length": self.step_length,
            "warmup": self.scenario.warmup,
            "end_time": self.end_time,
            "flows": [asdict(f) for f in self.scenario.flows],
            "events": [asdict(e) for e in self.scenario.events],
        }

    # --- one step ---------------------------------------------------------
    def step(self) -> None:
        t = self.t
        observation = self.sensors.observe(t, self.controller.observation_source)
        state = self.supervisor.state(t)
        action = self._ask(observation, state)
        safe = self.supervisor.validate(action, t)
        preempt = self._ev_requests() if self.ev_preemption else {}
        self._apply(self.supervisor.apply_safe_action(safe, t, preempt))
        self.conn.simulationStep()
        self.supervisor.tick(self.step_length)
        self.t = self.conn.simulation.getTime()
        departed = self.conn.simulation.getDepartedIDList()
        arrived = self.conn.simulation.getArrivedIDList()
        for vid in departed:
            if self.frames:
                self.conn.vehicle.subscribe(vid, VEHICLE_VARS)
            if self.conn.vehicle.getTypeID(vid) in EV_TYPES:
                self._ev_ids.add(vid)
        for vid in arrived:
            if vid in self._ev_ids:
                self._ev_ids.discard(vid)
                self.log_event("ev_arrived", vehicle=vid)
        self.sensors.on_step(self.t, departed, arrived)
        self.metrics.on_step(self.t, departed, arrived)
        self.runtime.on_step(self.t)
        self.controller.log(self.step_count)
        self.events.extend(self.controller.drain_events())
        self.step_count += 1

    def _ask(self, observation, state):
        start = time.perf_counter()
        try:
            self.controller.observe(observation)
            action = self.controller.propose_action(state)
        except Exception as exc:  # a failing controller must never stop the signals
            self.controller_errors += 1
            self.supervisor.record(self.t, None, "controller_error", detail=f"{type(exc).__name__}: {exc}")
            return self._fallback(observation, state)
        if time.perf_counter() - start > config.CONTROLLER_TIME_BUDGET_S:
            self.supervisor.record(self.t, None, "timeout", detail="controller exceeded its time budget")
            return self._fallback(observation, state)
        return action

    def _fallback(self, observation, state):
        self.fallback_steps += 1
        self.fallback.observe(observation)
        return self.fallback.propose_action(state)

    def _apply(self, signals: dict[str, str]) -> None:
        for j, signal in signals.items():
            if self._shown.get(j) == signal:
                continue
            state = build_state(self.topology.links[j], self.topology.n_links[j], signal)
            if not is_conflict_free(self.topology.links[j], state):  # SIG-01 guard, should never fire
                raise RuntimeError(f"conflicting greens at {j}: {state}")
            self.conn.trafficlight.setRedYellowGreenState(j, state)
            self._shown[j] = signal

    def _ev_requests(self) -> dict[str, str]:
        """Emergency vehicles within EV_PREEMPT_DISTANCE_M of a signal ask for their axis."""
        requests, active = {}, set()
        for vid in list(self._ev_ids):
            try:
                upcoming = self.conn.vehicle.getNextTLS(vid)
            except traci.TraCIException:
                self._ev_ids.discard(vid)
                continue
            if not upcoming:
                continue
            tls_id, link_index, dist, _ = upcoming[0]
            axis = self.topology.link_axis.get(tls_id, {}).get(link_index)
            if axis is None or dist > config.EV_PREEMPT_DISTANCE_M or tls_id in requests:
                continue
            requests[tls_id] = axis
            active.add((vid, tls_id))
            if (vid, tls_id) not in self._ev_active:
                self.preemptions.append({"t": self.t, "vehicle": vid, "junction": tls_id, "axis": axis, "distance": round(dist, 1)})
                self.log_event("preemption", vehicle=vid, junction=tls_id, axis=axis)
        self._ev_active = active
        return requests

    # --- events, frames and the signal-data API ------------------------------
    def log_event(self, event_type: str, /, **data) -> None:
        self.events.append({"t": self.t, "type": event_type, **data})

    def note_extra_vehicle(self) -> None:
        if self.scenario.warmup <= self.t < self.end_time:
            self.extra_in_window += 1

    def drain_events(self) -> list[dict]:
        new = self.events[self._event_cursor :]
        self._event_cursor = len(self.events)
        return new

    def signal_view(self) -> dict:
        view = {}
        for j, js in self.supervisor.junctions.items():
            view[j] = {
                "signal": js.signal,
                "axis": axis_of(js.signal),
                "colors": approach_colors(js.signal),
                "time_in_state": round(js.t_in, 1),
                "min_time_to_change": round(self.supervisor.min_time_to_change(j), 1),
                "preempted_by": js.preempted_by,
            }
        return view

    def frame(self) -> dict:
        vehicles = []
        if self.frames:
            for vid, r in self.conn.vehicle.getAllSubscriptionResults().items():
                if not r:
                    continue
                x, y = r[tc.VAR_POSITION]
                vtype = r[tc.VAR_TYPE]
                kind = vtype if vtype in DRAWN_TYPES else ("probe" if self.sensors.is_probe(vid) else "car")
                vehicles.append([vid, round(x, 2), round(y, 2), round(r[tc.VAR_ANGLE], 1), round(r[tc.VAR_SPEED], 2), kind])
        return {
            "t": self.t,
            "scenario": self.scenario.name,
            "controller": self.controller.name,
            "coverage": self.sensors.coverage,
            "ev_preemption": self.ev_preemption,
            "vehicles": vehicles,
            "signals": self.signal_view(),
            "kpi": self.metrics.live(),
            "events": self.drain_events(),
            "phantoms": self.sensors.phantom_positions(),
            "alerts": self.sensors.alerts(),
            "closures": self.runtime.closed_edges(),
            "attack": self.runtime.attack,
            "recommendation": self.controller.pending_recommendation(),
            "preempting": sorted({j for _, j in self._ev_active}),
        }

    def spat(self) -> dict:
        """Signal phase & timing, the kind of feed Busan shares with navigation apps."""
        return {"t": self.t, "source": "team-b-signal-twin", "junctions": self.signal_view()}

    def geometry(self) -> dict:
        return (self.topology if self.conn else load_topology()).geometry()

    def handle_command(self, command: dict) -> dict:
        kind = command.get("type")
        params = {k: v for k, v in command.items() if k != "type"}
        if kind == "set_coverage":
            self.sensors.set_coverage(float(params["value"]))
            self.coverage = self.sensors.coverage
            return {"ok": True, "coverage": self.coverage}
        if kind == "set_preemption":
            self.ev_preemption = bool(params.get("enabled", True))
            return {"ok": True, "ev_preemption": self.ev_preemption}
        if kind in EVENT_KINDS:  # every scenario event type is also a twin command
            return {"ok": True, "result": getattr(self.runtime, kind)(**params)}
        reply = self.controller.handle_command(command)
        return reply if reply is not None else {"ok": False, "error": f"unknown command '{kind}'"}

    # --- results ------------------------------------------------------------
    def close(self) -> dict:
        if self.summary is not None:
            return self.summary
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
        controller_summary = self.controller.summary()  # before close(), which may free its state
        self.controller.close()
        departs = getattr(self.scenario, "departs", [])
        planned = sum(1 for d in departs if self.scenario.warmup <= d < self.end_time) + self.extra_in_window
        metrics = self.metrics.finalize(self.tripinfo_path, planned_in_window=planned, events=self.events)
        trips = metrics.pop("trips")
        self.summary = {
            "run_id": self.run_id,
            "scenario": self.scenario.name,
            "controller": self.controller.name,
            "seed": self.seed,
            "coverage": self.coverage,
            "sampling": self.sampling,
            "ev_preemption": self.ev_preemption,
            "sim_time_s": self.t,
            "wall_time_s": round(time.time() - getattr(self, "_wall0", time.time()), 1),
            **metrics,
            "controller_errors": self.controller_errors,
            "fallback_steps": self.fallback_steps,
            "rejected_actions": self.supervisor.rejections if self.conn else 0,
            "preemptions": len(self.preemptions),
            "signal_switches": sum(1 for e in self.supervisor.events if e.reason in ("switch", "preempt")) if self.conn else 0,
        }
        if controller_summary is not None:
            self.summary["controller_summary"] = controller_summary
        if self.conn is not None:
            self._write_outputs(trips)
        return self.summary

    def _write_outputs(self, trips: list[dict]) -> None:
        out = self.output_dir
        (out / "summary.json").write_text(json.dumps(self.summary, indent=2))
        manifest = {
            "run_id": self.run_id,
            "created_unix": round(time.time()),
            "code_revision": _git_revision(),
            "sumo_version": self._sumo_version,
            "network_hash": file_hash(self._net_paths.net),
            "demand_hash": file_hash(self.routes_path),
            "seed": self.seed,
            "config": self.run_config(),
            "outputs": {
                "summary": "summary.json",
                "trips": "trips.csv",
                "signal_events": "signal_events.csv",
                "preemptions": "preemptions.json",
                "events": "events_report.json",
                "tripinfo": "tripinfo.xml",
            },
        }
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
        if trips:
            with open(out / "trips.csv", "w", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(trips[0]))
                writer.writeheader()
                writer.writerows(trips)
        with open(out / "signal_events.csv", "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["t", "junction", "requested", "executed", "reason", "detail"])
            for e in self.supervisor.events:
                writer.writerow([e.t, e.junction, e.requested, e.executed, e.reason, e.detail])
        (out / "preemptions.json").write_text(json.dumps(self.preemptions, indent=2))
        # per-emergency-vehicle dispatch → arrival times, closure/attack history, reroutes
        (out / "events_report.json").write_text(json.dumps(self.runtime.report(), indent=2, default=str))
