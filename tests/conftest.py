"""Shared pytest setup: the ``sumo`` marker for tests that start a SUMO simulation.

``pytest -m "not sumo"`` is the quick tier (no SUMO process). A test is marked automatically when
its own code, a fixture it uses, or a helper function of its module that it calls refers to
something that starts a simulation: SimEnv, run_one / run_matrix, record_run, TrainEnv /
PlanEvalEnv, SearchJob, the doctor smoke run (run_checks), an RL training episode
(run_episode), traci / libsumo, or a live twin session request (``/api/session?wait``).
Comments and docstrings do not count. The heuristic errs on the side of marking; add
``@pytest.mark.sumo`` by hand if it misses a test. The markers are registered in pyproject.toml.
"""
from __future__ import annotations

import inspect
import io
import textwrap
import tokenize

import pytest

SUMO_NAMES = frozenset({"SimEnv", "run_one", "run_matrix", "record_run", "TrainEnv", "PlanEvalEnv",
                        "SearchJob", "run_checks", "run_episode", "traci", "libsumo"})
SUMO_STRINGS = ("/api/session?wait",)


def _code_tokens(obj) -> tuple[set[str], list[str]]:
    """Identifiers and string literals in the source of ``obj`` (comments are dropped)."""
    try:
        src = textwrap.dedent(inspect.getsource(obj))
    except (OSError, TypeError):
        return set(), []
    names, strings = set(), []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.NAME:
                names.add(tok.string)
            elif tok.type == tokenize.STRING:
                strings.append(tok.string)
    except (tokenize.TokenError, SyntaxError):
        pass
    return names, strings


def starts_sumo(item) -> bool:
    func = getattr(item, "function", None)
    if func is None:
        return False
    module = getattr(item, "module", None)
    todo = [func]
    info = getattr(item, "_fixtureinfo", None)
    for defs in (info.name2fixturedefs.values() if info else ()):
        todo += [d.func for d in defs if not getattr(d.func, "__module__", "").startswith(("_pytest", "pytest"))]
    seen = set()
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        names, strings = _code_tokens(f)
        if names & SUMO_NAMES or any(marker in s for s in strings for marker in SUMO_STRINGS):
            return True
        if module is not None:  # follow helpers defined in the same test module
            for name in names:
                obj = vars(module).get(name)
                if inspect.isfunction(obj) and obj.__module__ == module.__name__:
                    todo.append(obj)
    return False


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.get_closest_marker("sumo") is None and starts_sumo(item):
            item.add_marker(pytest.mark.sumo)
