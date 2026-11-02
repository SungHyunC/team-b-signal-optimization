"""Evaluation: metrics for one run and the statistics used to compare runs.

Owner: Data & evaluation (Doyoung).

metrics.py      MetricsCollector (called by SimEnv every step; summary at the end of a run)
spillback.py    spillback with upstream-blocking evidence (not just a queue threshold)
recovery.py     recovery time after a closure / attack, excess delay
estimation.py   probe / detector estimates vs ground truth (MAE, RMSE, bias)
stats.py        t critical values, confidence intervals, paired differences, Holm correction

Formulas are explained in each module's docstring and in docs/roles/data-evaluation.md.
"""
