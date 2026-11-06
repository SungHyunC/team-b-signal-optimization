"""Audit completeness and reproducibility of paired-seed experiment runs from the folders alone.

This module reads the existing run_spec.json/summary.json/manifest.json files.
It never treats a missing, failed or truncated run as a successful statistical observation.

`audit_experiment` checks a scenario x controller x seed design against whatever run folders
exist (e.g. a subset of a larger experiment). Runs are identified by their full condition
(scenario variant, controller variant, coverage, sampling, preemption, end time), so coverage
sweeps, preemption on/off, controller-parameter variants and --counterfactual twins are separate
runs, not duplicates. When the exact run matrix is known, prefer
`teamb.experiments.accuracy.audit_specs` (what `run --strict-validation` uses), which also
compares every folder with its RunSpec.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from teamb.experiments.runner import run_status


def _identity(spec: dict, folder: Path) -> tuple:
    """(scenario variant, controller variant, coverage, sampling, preemption, end time, seed)."""
    scen = folder.name.split("__")[0] if spec.get("scenario_params") else spec["scenario"]
    cov = spec.get("coverage")
    end = spec.get("end_time")
    return (scen, spec.get("variant") or spec["controller"], 1.0 if cov is None else float(cov),
            spec.get("sampling") or "uniform", bool(spec.get("ev_preemption", True)),
            None if end is None else float(end), spec["seed"])


def audit_experiment(exp_dir: str | Path, *, scenarios: list[str],
                     controllers: list[str], seeds: list[int],
                     baseline: str = "fixed_time") -> dict:
    exp_dir = Path(exp_dir)
    if not scenarios or not controllers or not seeds:
        raise ValueError("scenarios, controllers and seeds must be nonempty")
    if baseline not in controllers:
        raise ValueError("baseline must be included in controllers")
    if len(set(seeds)) != len(seeds):
        raise ValueError("duplicate seeds are not allowed")
    if any(type(s) is not int or s < 0 for s in seeds):
        raise ValueError("seeds must be nonnegative integers")
    seen = defaultdict(list)  # (scenario, controller, seed) of the design -> folders
    by_identity = defaultdict(list)  # full run identity -> folders
    by_condition = defaultdict(lambda: defaultdict(set))  # condition -> controller variant -> valid seeds
    problems = []
    revisions, versions = set(), set()
    for folder in sorted((exp_dir / "runs").glob("*")):
        if not folder.is_dir():
            continue
        spec_file = folder / "run_spec.json"
        if not spec_file.exists():
            problems.append(f"{folder.name}: missing run_spec.json")
            continue
        try:
            spec = json.loads(spec_file.read_text())
            scenario, controller, seed = spec["scenario"], spec["controller"], spec["seed"]
            identity = _identity(spec, folder)
        except (ValueError, KeyError, TypeError) as exc:
            problems.append(f"{folder.name}: invalid run specification ({exc})")
            continue
        if scenario not in scenarios or controller not in controllers or seed not in seeds:
            continue
        seen[(scenario, controller, seed)].append(folder.name)
        by_identity[identity].append(folder.name)
        valid = True
        status, summary, reason = run_status(folder, expected_end=spec.get("end_time"))
        if summary is None and status != "failed":
            problems.append(f"{folder.name}: missing summary.json (failed or unfinished)")
            valid = False
        elif status == "failed":
            problems.append(f"{folder.name}: failed run ({reason})")
            valid = False
        elif status != "ok":
            problems.append(f"{folder.name}: run did not finish ({reason})")
            valid = False
        else:
            delay = summary.get("mean_delay_s")
            if not isinstance(delay, (int, float)) or isinstance(delay, bool):
                problems.append(f"{folder.name}: missing/non-numeric primary delay metric")
                valid = False
        manifest = folder / "manifest.json"
        if not manifest.exists():
            problems.append(f"{folder.name}: missing manifest.json")
        else:
            try:
                m = json.loads(manifest.read_text())
                if m.get("code_revision"):
                    revisions.add(str(m["code_revision"]))
                else:
                    problems.append(f"{folder.name}: missing code revision")
                if m.get("sumo_version"):
                    versions.add(str(m["sumo_version"]))
                else:
                    problems.append(f"{folder.name}: missing SUMO version")
            except ValueError:
                problems.append(f"{folder.name}: invalid manifest.json")
        if valid:
            scen, variant, cov, sampling, pre, end, _ = identity
            by_condition[(scen, cov, sampling, pre, end)][variant].add(seed)
    expected = [(sc, ctrl, seed) for sc in scenarios for ctrl in controllers for seed in seeds]
    missing = [{"scenario": sc, "controller": ctrl, "seed": seed}
               for sc, ctrl, seed in expected if (sc, ctrl, seed) not in seen]
    duplicates = [{"scenario": ident[0], "controller": ident[1], "seed": ident[-1], "folders": names}
                  for ident, names in by_identity.items() if len(names) > 1]
    unpaired = [{"condition": list(cond), "seeds": {c: sorted(s) for c, s in ctrls.items()}}
                for cond, ctrls in by_condition.items() if len({frozenset(s) for s in ctrls.values()}) > 1]
    if len(revisions) > 1:
        problems.append("mixed code revisions across runs")
    if len(versions) > 1:
        problems.append("mixed SUMO versions across runs")
    if duplicates:
        problems.append("duplicate runs of the same condition, controller and seed")
    if missing:
        problems.append(f"{len(missing)} expected runs are missing")
    if unpaired:
        problems.append(f"unpaired seeds in {len(unpaired)} condition(s)")
    report = {"complete": not problems, "expected_runs": len(expected),
              "found_runs": sum(1 for key in expected if key in seen),
              "missing_runs": missing, "duplicates": duplicates, "unpaired": unpaired,
              "problems": problems, "code_revisions": sorted(revisions),
              "sumo_versions": sorted(versions),
              "design": {"scenarios": scenarios, "controllers": controllers,
                         "seeds": seeds, "baseline": baseline}}
    return report
