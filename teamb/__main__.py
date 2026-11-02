"""Command line entry point: `python -m teamb <command>`.

  build-net                  generate the SUMO network (done automatically on first run)
  list                       available controllers and scenarios
  run                        one headless run, prints the summary
  twin                       start the digital twin web app

Batch experiments and reports: `python -m teamb.experiments --help`.
"""
from __future__ import annotations

import argparse
import json


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="python -m teamb", description="Team B signal twin")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build-net", help="generate the SUMO network")
    sub.add_parser("list", help="list controllers and scenarios")
    run = sub.add_parser("run", help="one headless simulation")
    run.add_argument("--scenario", default="rush_hour")
    run.add_argument("--controller", default="fixed_time")
    run.add_argument("--seed", type=int, default=1)
    run.add_argument("--coverage", type=float, default=None, help="share of vehicles reporting navigation data (0-1)")
    run.add_argument("--end", type=float, default=None, help="stop at this simulation time (s)")
    run.add_argument("--no-preemption", action="store_true", help="disable emergency-vehicle preemption")
    twin = sub.add_parser("twin", help="start the digital twin web app")
    twin.add_argument("--host", default="127.0.0.1")
    twin.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    if args.command == "build-net":
        from teamb.network.build import ensure_network

        paths = ensure_network(force=True)
        print(f"network:   {paths.net}\ndetectors: {paths.detectors}")
    elif args.command == "list":
        from teamb.controllers import available as controllers
        from teamb.scenarios import available as scenarios

        print(json.dumps({"controllers": controllers(), "scenarios": scenarios()}, indent=2, ensure_ascii=False))
    elif args.command == "run":
        from teamb.sim.env import SimEnv

        env = SimEnv(
            args.scenario,
            args.controller,
            seed=args.seed,
            coverage=args.coverage,
            end_time=args.end,
            ev_preemption=not args.no_preemption,
        )
        summary = env.run()
        print(json.dumps(summary, indent=2))
        print(f"\noutputs: {env.output_dir}")
    elif args.command == "twin":
        from teamb.twin.server import main as serve

        serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
