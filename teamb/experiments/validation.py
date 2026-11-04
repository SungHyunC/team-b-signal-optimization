"""Audit completeness and reproducibility of paired-seed experiment runs.

This module reads the existing run_spec.json/summary.json/manifest.json files.
It never treats a missing or failed run as a successful statistical observation.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


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
    seen = defaultdict(list)
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
        except (ValueError, KeyError, TypeError) as exc:
            problems.append(f"{folder.name}: invalid run specification ({exc})")
            continue
        if scenario not in scenarios or controller not in controllers or seed not in seeds:
            continue
        key = (scenario, controller, seed)
        seen[key].append(folder.name)
        if not (folder / "summary.json").exists():
            problems.append(f"{folder.name}: missing summary.json (failed or unfinished)")
        else:
            try:
                summary = json.loads((folder / "summary.json").read_text())
                delay = summary.get("mean_delay_s")
                if not isinstance(delay, (int, float)) or isinstance(delay, bool):
                    problems.append(f"{folder.name}: missing/non-numeric primary delay metric")
            except ValueError:
                problems.append(f"{folder.name}: invalid summary.json")
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
    expected = [(sc, ctrl, seed) for sc in scenarios for ctrl in controllers for seed in seeds]
    missing = [{"scenario": sc, "controller": ctrl, "seed": seed}
               for sc, ctrl, seed in expected if (sc, ctrl, seed) not in seen]
    duplicates = [{"scenario": sc, "controller": ctrl, "seed": seed, "folders": names}
                  for (sc, ctrl, seed), names in seen.items() if len(names) > 1]
    if len(revisions) > 1:
        problems.append("mixed code revisions across runs")
    if len(versions) > 1:
        problems.append("mixed SUMO versions across runs")
    if duplicates:
        problems.append("duplicate scenario/controller/seed runs")
    if missing:
        problems.append(f"{len(missing)} expected runs are missing")
    report = {"complete": not problems, "expected_runs": len(expected),
              "found_runs": sum(1 for key in expected if key in seen),
              "missing_runs": missing, "duplicates": duplicates,
              "problems": problems, "code_revisions": sorted(revisions),
              "sumo_versions": sorted(versions),
              "design": {"scenarios": scenarios, "controllers": controllers,
                         "seeds": seeds, "baseline": baseline}}
    return report
