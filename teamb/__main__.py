"""Command line entry point: ``teamb <command>`` (or ``python -m teamb <command>``).

Everyday commands
  twin                       start the digital twin web app (http://127.0.0.1:8000)
  run                        one headless simulation, prints the summary
  list                       available controllers and scenarios
  doctor                     check the installation (Python, SUMO, network, optional extras)

Research workflow
  exp ...                    batch experiments and paired reports   (= python -m teamb.experiments)
  impact ...                 impact & cost-benefit table             (= python -m teamb.analysis.impact)
  diagnose ...               controller failure diagnosis            (= python -m teamb.experiments.diagnose)
  sandbox ...                validate / run a Scenario Sandbox JSON export
  train-rl ...               train the Q-learning controller         (= python -m teamb.controllers.rl_train)

Demo and maintenance
  site ...                   record / publish the online demo        (= python -m teamb.twin.site)
  vendor                     save three.js locally for offline demos (= python -m teamb.twin.vendor)
  build-net                  regenerate the SUMO network (done automatically on first run)

Run ``teamb <command> --help`` for the options of each command.
"""
from __future__ import annotations

import argparse
import json
import sys


def _experiments(argv: list[str]) -> int:
    from teamb.experiments.__main__ import main

    return main(argv)


def _impact(argv: list[str]) -> int:
    from teamb.analysis.impact import main

    return main(argv)


def _diagnose(argv: list[str]) -> int:
    from teamb.experiments.diagnose import main

    return main(argv)


def _site(argv: list[str]) -> int:
    from teamb.twin.site import main

    return main(argv)


def _vendor(argv: list[str]) -> int:
    if argv and argv[0] in ("-h", "--help"):
        print("usage: teamb vendor\n\nDownload the pinned three.js files into teamb/twin/static/vendor/ for offline demos.")
        return 0
    from teamb.twin.vendor import main

    return main()


def _train_rl(argv: list[str]) -> int:
    from teamb.controllers.rl_train import main

    main(argv)
    return 0


def _sandbox(argv: list[str]) -> int:
    from teamb.sandbox import main

    return main(argv)


# commands whose arguments are parsed by another module's own CLI
DELEGATES = {
    "exp": (_experiments, "batch experiments and paired reports"),
    "experiments": (_experiments, None),  # alias
    "impact": (_impact, "impact & cost-benefit table from an experiment"),
    "diagnose": (_diagnose, "read-only controller failure diagnosis of an experiment"),
    "sandbox": (_sandbox, "validate or run a Scenario Sandbox JSON export"),
    "train-rl": (_train_rl, "train the tabular Q-learning controller"),
    "site": (_site, "record, serve or publish the online demo"),
    "vendor": (_vendor, "save three.js locally for offline demos"),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="teamb",
        description="Team B traffic-signal digital twin (SUMO). Also available as `python -m teamb`.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run `teamb <command> --help` for the options of each command.",
    )
    from teamb import __version__

    parser.add_argument("--version", action="version", version=f"teamb {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")
    twin = sub.add_parser("twin", help="start the digital twin web app")
    twin.add_argument("--host", default="127.0.0.1")
    twin.add_argument("--port", type=int, default=8000)
    run = sub.add_parser("run", help="one headless simulation")
    run.add_argument("--scenario", default="rush_hour")
    run.add_argument("--controller", default="fixed_time")
    run.add_argument("--seed", type=int, default=1)
    run.add_argument("--coverage", type=float, default=None, help="share of vehicles reporting navigation data (0-1)")
    run.add_argument("--end", type=float, default=None, help="stop at this simulation time (s)")
    run.add_argument("--no-preemption", action="store_true", help="disable emergency-vehicle preemption")
    run.add_argument("--controller-params", default=None, help='JSON object, e.g. \'{"interval": 5}\'')
    run.add_argument("--scenario-params", default=None, help='JSON object, e.g. \'{"demand_scale": 1.25}\'')
    sub.add_parser("list", help="list controllers and scenarios")
    doctor = sub.add_parser("doctor", help="check the installation")
    doctor.add_argument("--skip-sim", action="store_true", help="do not run the 60 s smoke simulation")
    sub.add_parser("build-net", help="regenerate the SUMO network")
    for name, (_, help_text) in DELEGATES.items():
        if help_text:
            sub.add_parser(name, help=help_text, add_help=False)
    return parser


def _json_arg(text: str | None, flag: str) -> dict | None:
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{flag}: invalid JSON ({exc})") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{flag}: expected a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in DELEGATES:
        return int(DELEGATES[argv[0]][0](argv[1:]) or 0)
    args = _parser().parse_args(argv)

    if args.command == "build-net":
        from teamb.network.build import ensure_network

        paths = ensure_network(force=True)
        print(f"network:   {paths.net}\ndetectors: {paths.detectors}")
    elif args.command == "list":
        from teamb.controllers import available as controllers
        from teamb.scenarios import available as scenarios

        print(json.dumps({"controllers": controllers(), "scenarios": scenarios()}, indent=2, ensure_ascii=False))
    elif args.command == "doctor":
        from teamb.doctor import run_checks

        return run_checks(simulate=not args.skip_sim)
    elif args.command == "run":
        from teamb.sim.env import SimEnv

        env = SimEnv(
            args.scenario,
            args.controller,
            seed=args.seed,
            coverage=args.coverage,
            end_time=args.end,
            ev_preemption=not args.no_preemption,
            controller_params=_json_arg(args.controller_params, "--controller-params"),
            scenario_params=_json_arg(args.scenario_params, "--scenario-params"),
        )
        summary = env.run()
        print(json.dumps(summary, indent=2))
        print(f"\noutputs: {env.output_dir}")
    elif args.command == "twin":
        from teamb.twin.server import main as serve

        serve(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
