"""Batch experiments and paired reports.

Owner: Data & evaluation (Doyoung).

    python -m teamb.experiments run --name sample --scenarios rush_hour,emergency \\
        --controllers fixed_time,coordinated --seeds 1-3 --end 2700
    python -m teamb.experiments report --name sample

runner.py    the matrix (scenarios x controllers x seeds x coverages x sampling x preemption),
             parallel worker processes (default: CPU cores - 1), one SimEnv(...).run() per run,
             run completeness and resume/skip
analysis.py  summary.csv, paired analysis vs a baseline controller (matched seeds, 95 % CI,
             Holm-corrected p-values), coverage sweep, estimation, EV, security, recovery,
             PERF-01 and compute-cost tables; report.json (schema for the twin) and report.md

Results go to results/experiments/<name>/ (see results/README.md).
"""
from teamb.experiments.runner import RunSpec, build_matrix, run_matrix  # noqa: F401
