"""Strict, dimension-aware quality gate for paired SUMO experiments."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from teamb.experiments.runner import RunSpec


def audit_specs(exp_dir: str | Path, specs: list[RunSpec], *, metric: str = "mean_delay_s") -> dict:
    """Check exact run identity, outputs, software provenance and paired-seed coverage.

    Does not substitute a different coverage, sampling strategy, preemption mode,
    controller parameter set or simulation end time for a missing observation.
    """
    exp_dir = Path(exp_dir)
    names = [s.name for s in specs]
    if len(names) != len(set(names)):
        raise ValueError("duplicate run names in the expected experiment matrix")
    problems = []
    passed = set()
    revisions, versions, networks = set(), set(), set()
    by_group = defaultdict(set)
    for spec in specs:
        folder = exp_dir / "runs" / spec.name
        if not folder.is_dir():
            problems.append(f"{spec.name}: missing run directory")
            continue
        try:
            saved = json.loads((folder / "run_spec.json").read_text())
            for key in ("scenario", "controller", "seed", "coverage", "sampling", "ev_preemption",
                        "end_time", "controller_params", "scenario_params"):
                if saved.get(key) != getattr(spec, key):
                    raise ValueError(f"run specification mismatch: {key}")
            summary = json.loads((folder / "summary.json").read_text())
            value = summary.get(metric)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"invalid {metric}")
            if (folder / "error.json").exists():
                raise ValueError("error.json present; run may have failed")
            manifest = json.loads((folder / "manifest.json").read_text())
            for key, target in (("code_revision", revisions), ("sumo_version", versions),
                                ("network_hash", networks)):
                val = manifest.get(key)
                if not val or val == "unknown":
                    raise ValueError(f"missing or unknown {key}")
                target.add(str(val))
            if manifest.get("seed") != spec.seed:
                raise ValueError("manifest seed does not match requested seed")
        except (OSError, ValueError, TypeError) as exc:
            problems.append(f"{spec.name}: {exc}")
            continue
        passed.add(spec.name)
        group = (spec.scenario_variant, spec.variant, spec.coverage, spec.sampling,
                 spec.ev_preemption, spec.end_time)
        by_group[group].add(spec.seed)
    for label, values in (("code revisions", revisions), ("SUMO versions", versions), ("network hashes", networks)):
        if len(values) > 1:
            problems.append(f"mixed {label}: {sorted(values)}")
    # Every controller group must contain the exact same seed set as its peers.
    by_condition = defaultdict(list)
    for (scenario, controller, coverage, sampling, preemption, end_time), seeds in by_group.items():
        by_condition[(scenario, coverage, sampling, preemption, end_time)].append((controller, seeds))
    for condition, controllers in by_condition.items():
        if len({frozenset(seeds) for _, seeds in controllers}) > 1:
            problems.append(f"unpaired seeds for condition {condition}")
    return {
        "complete": not problems and len(passed) == len(specs),
        "expected_runs": len(specs), "valid_runs": len(passed),
        "invalid_or_missing": sorted(set(names) - passed),
        "problems": problems,
        "code_revisions": sorted(revisions), "sumo_versions": sorted(versions),
        "network_hashes": sorted(networks),
        "metric": metric,
    }
