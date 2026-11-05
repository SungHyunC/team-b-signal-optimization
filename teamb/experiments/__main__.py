"""Command line: `python -m teamb.experiments run|report|list`.

Examples
--------
Sample experiment (the one in docs/results/sample-report.md)::

    python -m teamb.experiments run --name sample --scenarios rush_hour,emergency \\
        --controllers fixed_time,coordinated --seeds 1-3 --end 2700 --workers 2

Coverage sweep with biased sampling (probe-based controller vs fixed-time)::

    python -m teamb.experiments run --name sweep --scenarios rush_hour --controllers fixed_time \\
        --seeds 1-5 --coverages 1.0
    python -m teamb.experiments run --name sweep --scenarios rush_hour --controllers max_pressure \\
        --seeds 1-5 --coverages 10,25,50,75,100 --sampling uniform,approach_biased,speed_biased

EV preemption on vs off (clean "extra delay for others")::

    python -m teamb.experiments run --name ev --scenarios emergency --controllers coordinated \\
        --seeds 1-5 --ev-preemption on,off

Report again (e.g. with another baseline) without re-running::

    python -m teamb.experiments report --name sample --baseline coordinated
"""
from __future__ import annotations

import argparse
import json
import shlex
import shutil
import sys
from pathlib import Path

from teamb.experiments.analysis import write_report
from teamb.experiments.accuracy import audit_specs
from teamb.experiments.runner import EXPERIMENTS_DIR, build_matrix, parse_coverages, parse_seeds, run_matrix, validate_matrix


def _csv(text: str) -> list[str]:
    return [p.strip() for p in str(text).split(",") if p.strip()]


def _onoff(text: str) -> list[bool]:
    out = []
    for p in _csv(text):
        if p.lower() in ("on", "true", "1", "yes"):
            out.append(True)
        elif p.lower() in ("off", "false", "0", "no"):
            out.append(False)
        else:
            raise argparse.ArgumentTypeError(f"--ev-preemption expects on/off, got '{p}'")
    return out


def _json(text: str | None) -> dict:
    if not text:
        return {}
    path = Path(text)
    value = json.loads(path.read_text()) if path.exists() else json.loads(text)
    if not isinstance(value, dict):
        raise argparse.ArgumentTypeError("expected a JSON object")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m teamb.experiments", description="Team B batch experiments")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a matrix of simulations, then write the report")
    run.add_argument("--name", required=True, help="experiment name (folder under results/experiments/)")
    run.add_argument("--scenarios", default="rush_hour", help="comma-separated scenario names")
    run.add_argument("--controllers", default="fixed_time,coordinated", help="comma-separated controller names")
    run.add_argument("--seeds", default="1-3", help="e.g. 1-20 or 1,2,5")
    run.add_argument("--coverages", default="default",
                     help="probe coverage(s), 0-1 or percent: 10,25,50,75,100; 'default' = the scenario's default")
    run.add_argument("--sampling", default="uniform", help="uniform, approach_biased[:ratio], speed_biased[:p] (comma-separated)")
    run.add_argument("--ev-preemption", default="on", type=_onoff, help="on, off or on,off")
    run.add_argument("--end", type=float, default=None, help="simulation end time in s (default: the scenario's duration)")
    run.add_argument("--controller-params", type=_json, default=None,
                     help='JSON (or a .json file): {"param": v} for all controllers or {"controller": {"param": v}}')
    run.add_argument("--scenario-params", type=_json, default=None, help='JSON, e.g. {"demand_scale": 1.2} or {"warmup": 300}')
    run.add_argument("--counterfactual", action="store_true",
                     help="also run every scenario that has events without them (reference for recovery time)")
    run.add_argument("--workers", type=int, default=2, help="parallel simulations (each is one SUMO process)")
    run.add_argument("--baseline", default="fixed_time", help="controller the others are compared with")
    run.add_argument("--force", action="store_true", help="re-run runs that already have results")
    run.add_argument("--no-report", action="store_true", help="only run, do not write the report")
    run.add_argument("--dry-run", action="store_true", help="print the run list and exit")
    run.add_argument("--strict-validation", action="store_true", help="audit every expected run and fail on incomplete or inconsistent results")

    rep = sub.add_parser("report", help="(re)write summary.csv, report.json and report.md")
    rep.add_argument("--name", required=True)
    rep.add_argument("--baseline", default="fixed_time")
    rep.add_argument("--copy-to", default=None, help="also copy report.md here (e.g. docs/results/sample-report.md)")

    sub.add_parser("list", help="list experiments in results/experiments/")
    args = parser.parse_args(argv)

    if args.command == "list":
        for d in sorted(EXPERIMENTS_DIR.glob("*/")):
            n = len(list((d / "runs").glob("*/summary.json")))
            print(f"{d.name}: {n} finished runs" + (" · report.md" if (d / "report.md").exists() else ""))
        return 0

    exp_dir = EXPERIMENTS_DIR / args.name
    if args.command == "report":
        if not (exp_dir / "runs").exists():
            print(f"no runs in {exp_dir}", file=sys.stderr)
            return 1
        report = write_report(exp_dir, baseline=args.baseline)
        print(f"{len(report['rows'])} rows -> {exp_dir / 'report.md'}")
        if args.copy_to:
            shutil.copyfile(exp_dir / "report.md", args.copy_to)
            print(f"copied to {args.copy_to}")
        return 0

    specs = build_matrix(
        _csv(args.scenarios), _csv(args.controllers), parse_seeds(args.seeds), parse_coverages(args.coverages),
        _csv(args.sampling), args.ev_preemption, args.end, args.controller_params, args.scenario_params,
        counterfactual=args.counterfactual,
    )
    problems = validate_matrix(specs)
    if problems:
        print("cannot run:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 2
    if args.dry_run:
        for s in specs:
            print(s.name)
        print(f"{len(specs)} runs")
        return 0
    print(f"{len(specs)} runs -> {exp_dir} ({args.workers} workers)")
    command = "python -m teamb.experiments " + " ".join(shlex.quote(a) for a in (argv if argv is not None else sys.argv[1:]))
    record = run_matrix(specs, exp_dir, workers=args.workers, force=args.force, command=command)
    print(f"done in {record['wall_time_s']} s: {record['ok']} ok, {record['skipped']} skipped, {len(record['failed'])} failed")
    if args.strict_validation:
        audit = audit_specs(exp_dir, specs)
        (exp_dir / "validation.json").write_text(json.dumps(audit, indent=2))
        print(f"validation: {audit['valid_runs']}/{audit['expected_runs']} valid runs")
        if not audit["complete"]:
            for issue in audit["problems"][:30]:
                print(f"  INVALID: {issue}", file=sys.stderr)
            return 3
    if not args.no_report:
        report = write_report(exp_dir, baseline=args.baseline)
        print(f"report: {exp_dir / 'report.md'} ({len(report['rows'])} rows)")
    return 1 if record["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
