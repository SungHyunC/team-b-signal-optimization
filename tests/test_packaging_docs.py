"""Documentation stays navigable and honest.

- Every relative link in a tracked Markdown file points at a file or folder that exists.
- Every Markdown file under docs/ is reachable from README.md through relative links.
- Documented `teamb exp run` / `python -m teamb.experiments run` commands still pass --dry-run
  (put `<!-- docs-check: skip -->` on the line before a fenced block that must not be checked,
  e.g. a command that needs another branch).
- The cloud deployment guide documents every TWIN_* switch and matches render.yaml.
- Study evidence is committed under docs/results/studies/, not only in expiring Actions artifacts.
"""
from __future__ import annotations

import contextlib
import csv
import io
import json
import re
import shlex
import subprocess
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
STUDIES = DOCS / "results" / "studies"
SKIP_DIRS = {".git", ".venv", "node_modules", "site", "build", "dist", "results"}

LINK = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
REF_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s+.*)?$")
FENCE = re.compile(r"^\s*(```|~~~)")
EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|#)", re.I)


def _markdown_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--", "*.md"], cwd=ROOT, capture_output=True,
                             text=True, check=True, timeout=30).stdout
        files = [ROOT / p for p in out.split("\0") if p]
    except (OSError, subprocess.SubprocessError):
        files = [p for p in ROOT.rglob("*.md") if not SKIP_DIRS & set(p.relative_to(ROOT).parts[:-1])]
    files = [p for p in files if p.exists()]
    assert files, "no Markdown files found"
    return sorted(files)


def _prose_lines(text: str):
    """(line number, line) outside fenced code blocks, with inline code removed."""
    fenced = False
    for no, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            yield no, re.sub(r"`[^`]*`", "", line)


def _relative_links(md: Path):
    for no, line in _prose_lines(md.read_text(encoding="utf-8")):
        targets = LINK.findall(line)
        ref = REF_DEF.match(line)
        if ref:
            targets.append(ref.group(1))
        for target in targets:
            if not EXTERNAL.match(target):
                yield no, target


def _resolve(md: Path, target: str) -> Path:
    path = unquote(target.split("#", 1)[0].split("?", 1)[0])
    return (ROOT / path.lstrip("/")) if path.startswith("/") else (md.parent / path)


MARKDOWN = _markdown_files()


def test_relative_links_resolve():
    broken = []
    for md in MARKDOWN:
        for no, target in _relative_links(md):
            dest = _resolve(md, target)
            if not dest.exists():
                broken.append(f"{md.relative_to(ROOT)}:{no}: {target}")
            elif ROOT not in dest.resolve().parents and dest.resolve() != ROOT:
                broken.append(f"{md.relative_to(ROOT)}:{no}: {target} (outside the repository)")
    assert not broken, "broken relative links:\n" + "\n".join(broken)


def test_link_checker_catches_broken_links(tmp_path):
    md = tmp_path / "x.md"
    (tmp_path / "ok.md").write_text("ok")
    md.write_text("[a](ok.md) [b](missing.md#x) ![c](img/none.png) [d](https://example.com) [e](#top)\n"
                  "`[f](inline-code.md)`\n```\n[g](fenced.md)\n```\n[h]: other/missing.md\n")
    found = [t for _, t in _relative_links(md)]
    assert found == ["ok.md", "missing.md#x", "img/none.png", "other/missing.md"]
    assert [t for t in found if not _resolve(md, t).exists()] == ["missing.md#x", "img/none.png", "other/missing.md"]


def test_every_docs_page_is_reachable_from_the_readme():
    seen, todo = set(), [ROOT / "README.md"]
    while todo:
        md = todo.pop().resolve()
        if md in seen or not md.exists():
            continue
        seen.add(md)
        for _, target in _relative_links(md):
            dest = _resolve(md, target)
            if dest.is_dir():
                dest = dest / "README.md"
            if dest.suffix == ".md":
                todo.append(dest)
    orphans = [str(p.relative_to(ROOT)) for p in MARKDOWN if DOCS in p.parents and p.resolve() not in seen]
    assert not orphans, "not linked from README.md or the docs hub (docs/README.md):\n" + "\n".join(orphans)


def _experiment_commands():
    """`... experiments run ...` commands in fenced bash/sh/console blocks of the docs."""
    for md in MARKDOWN:
        if STUDIES in md.parents:  # archived reports reproduce their own (research) commit
            continue
        lines = md.read_text(encoding="utf-8").splitlines()
        i = 0
        while i < len(lines):
            m = FENCE.match(lines[i])
            if not m:
                i += 1
                continue
            lang = lines[i].strip()[3:].strip().lower()
            skip = i > 0 and "docs-check: skip" in lines[i - 1]
            j = i + 1
            block = []
            while j < len(lines) and not lines[j].strip().startswith(m.group(1)):
                block.append(lines[j])
                j += 1
            i = j + 1
            if skip or lang not in ("bash", "sh", "shell", "console", "powershell", ""):
                continue
            joined = re.sub(r"\\\n\s*", " ", "\n".join(block))
            for no, cmd in enumerate(joined.splitlines()):
                cmd = cmd.strip().removeprefix("$ ")
                if re.match(r"^(teamb (exp|experiments)|(python3?|py(\s+-3\.\d+)?)\s+-m\s+teamb(\.experiments|\s+exp)) run\b", cmd):
                    if "..." in cmd or "<" in cmd:  # placeholders
                        continue
                    yield f"{md.relative_to(ROOT)}: {cmd}", cmd


COMMANDS = list(_experiment_commands())


def test_found_documented_experiment_commands():
    assert len(COMMANDS) >= 5, COMMANDS


@pytest.mark.parametrize("where,cmd", COMMANDS, ids=[w[:90] for w, _ in COMMANDS])
def test_documented_experiment_command_dry_runs(where, cmd):
    from teamb.experiments.__main__ import main

    args = shlex.split(cmd, comments=True)
    args = args[args.index("run"):]
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = main(args + ["--dry-run"])
    except SystemExit as exc:  # argparse errors and explicit exits
        code = exc.code
    assert code in (0, None), f"{where}\n{out.getvalue()[-2000:]}"


NODE_TEST = re.compile(r"\bnode --test\b((?:[ \t]+[^\s#`'\"|;&)]+)*)")


def _undirected_node_tests(text: str) -> list[str]:
    """`node --test` commands that do not name test files: no argument, or a directory.

    Node 21+ reads each argument as a glob, so `node --test tests/js/` runs the directory itself as
    one failing "test"; `node --test tests/js/*.test.mjs` works on Node 20 and 21+."""
    bad = []
    for m in NODE_TEST.finditer(text):
        files = [a for a in m.group(1).split() if not a.startswith("-")]
        if not files or any(a.endswith("/") or (ROOT / a).is_dir() for a in files):
            bad.append(m.group(0).strip())
    return bad


def test_node_test_checker_catches_directory_arguments():
    sample = ("node --test tests/js/   # x\n`node --test tests`\nnode --test\n"
              "node --test tests/js/*.test.mjs   # ok\nrun: node --test --test-reporter=spec tests/js/a.test.mjs\n")
    assert _undirected_node_tests(sample) == ["node --test tests/js/", "node --test tests", "node --test"]


def test_documented_node_test_commands_name_files():
    sources = MARKDOWN + sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    bad = [f"{p.relative_to(ROOT)}: {cmd}" for p in sources for cmd in _undirected_node_tests(p.read_text(encoding="utf-8"))]
    assert not bad, "name the test files, e.g. `node --test tests/js/*.test.mjs`:\n" + "\n".join(bad)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "node --test tests/js/*.test.mjs" in readme


def test_fast_extra_row_says_which_commands_use_libsumo(monkeypatch):
    """The README must not claim TraCI everywhere when batch runs switch to libsumo on their own."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    (row,) = [line for line in readme.splitlines() if line.startswith("| `fast` |")]
    assert "TEAMB_TRACI_BACKEND" in row and "--traci-backend" in row, row
    assert "SimEnv, `teamb run` and the twin default to TraCI" in row, row
    from teamb.experiments import runner

    batch_default = getattr(runner, "batch_traci_backend", None)
    monkeypatch.delenv("TEAMB_TRACI_BACKEND", raising=False)
    if batch_default is not None and batch_default() == "auto":
        assert "`teamb exp run` and `teamb sandbox run` use it automatically" in row, row
        assert "default stays TraCI" not in row, row


def test_twin_environment_switches_are_documented():
    guide = (DOCS / "cloud-live-sumo-deployment.md").read_text(encoding="utf-8")
    names = set()
    for py in (ROOT / "teamb" / "twin").glob("*.py"):
        names |= set(re.findall(r"""(?:getenv|environ\.get|environ\[)\(?\s*["'](TWIN_[A-Z0-9_]+)""", py.read_text(encoding="utf-8")))
    assert {"TWIN_ACCESS_TOKEN", "TWIN_COOKIE_INSECURE"} <= names
    missing = sorted(n for n in names if n not in guide)
    assert not missing, f"document these in docs/cloud-live-sumo-deployment.md: {missing}"


def test_deployment_guide_matches_render_blueprint():
    yaml = pytest.importorskip("yaml")
    guide = (DOCS / "cloud-live-sumo-deployment.md").read_text(encoding="utf-8")
    (svc,) = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))["services"]
    assert "not yet hosted" not in guide.lower()
    assert f"`{svc['name']}`" in guide, "say which service render.yaml creates"
    assert f"**{svc['plan'].capitalize()}**" in guide, "name render.yaml's plan in the guide"


def test_no_links_to_expiring_actions_artifacts():
    offenders = [f"{md.relative_to(ROOT)}:{no}" for md in MARKDOWN
                 for no, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1)
                 if re.search(r"actions/runs/\d+/artifacts/\d+", line)]
    assert not offenders, "Actions artifacts expire; link docs/results/studies/ instead: " + ", ".join(offenders)


# study folder -> {experiment folder: expected strict-valid runs}
STUDY_RUNS = {
    "baseline-180": {"lesson1_validation": 180, "lesson1_smoke": 2},
    "robustness-360": {"robustness_low": 180, "robustness_high": 180,
                       "robustness_pilot_low": 6, "robustness_pilot_high": 6},
    "controller-pilot-15": {"congestion_pilot_heavy": 9, "congestion_pilot_nominal": 6},
    "calibration-24": {f"mild_{p}_{s}": 6 for p in ("110", "125") for s in ("closure", "rush")},
    "confirmation-360": {f"confirm_{c}": 60 for c in ("closure_125", "closure_075", "rush_100", "rush_125",
                                                      "emergency_100", "emergency_125")},
}
# headline run counts quoted in the reviews (pilots and smoke runs excluded)
STUDY_TOTALS = {"baseline-180": 180, "robustness-360": 360, "controller-pilot-15": 15,
                "calibration-24": 24, "confirmation-360": 360}


# Studies run on Modal (`teamb exp run --backend modal`) instead of GitHub Actions: their README
# names the code revision instead of a workflow run; confirmation studies carry strict audits.
CLOUD_STUDIES = {"controller-confirmation-2026-11": {"demand-0.75": 1260, "demand-1": 1260, "demand-1.25": 1260},
                 "rl-retraining-2026-11": {}}


def test_study_archives_are_committed_and_small():
    studies = sorted(p for p in STUDIES.iterdir() if p.is_dir())
    names = {p.name for p in studies}
    assert set(STUDY_RUNS) | {"congestion-diagnosis"} <= names
    assert names - set(STUDY_RUNS) - {"congestion-diagnosis"} <= set(CLOUD_STUDIES), "new study folders need a test entry"
    for study, total in STUDY_TOTALS.items():
        counted = sum(n for e, n in STUDY_RUNS[study].items() if "smoke" not in e and "robustness_pilot" not in e)
        assert counted == total, study
    for name in ("high_demand.json", "light_demand.json"):
        diagnosis = json.loads((STUDIES / "congestion-diagnosis" / name).read_text(encoding="utf-8"))
        assert diagnosis["run_count"] == 180
        assert all(s["paired_seeds"] == 30 for s in diagnosis["scenarios"].values())
    total = 0
    for study in studies:
        readme = (study / "README.md").read_text(encoding="utf-8")
        provenance = r"Modal" if study.name in CLOUD_STUDIES else r"actions/runs/\d+"
        assert re.search(provenance, readme) and re.search(r"\b[0-9a-f]{7,40}\b", readme), study.name
        for f in study.rglob("*"):
            if f.is_file():
                assert f.suffix in (".json", ".md", ".csv"), f
                total += f.stat().st_size
    assert total < 8 * 1024 * 1024, f"study archives grew to {total / 1e6:.1f} MB"


@pytest.mark.parametrize("study,experiment,runs", [(s, e, n) for s, d in STUDY_RUNS.items() for e, n in d.items()])
def test_study_experiments_are_complete_and_strict_valid(study, experiment, runs):
    folder = STUDIES / study / experiment
    audit = json.loads((folder / "validation.json").read_text(encoding="utf-8"))
    assert audit["complete"] and audit["valid_runs"] == runs, audit
    with open(folder / "summary.csv", newline="", encoding="utf-8") as fh:
        assert len(list(csv.DictReader(fh))) == runs
    assert json.loads((folder / "report.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("study,experiment,runs", [(s, e, n) for s, d in CLOUD_STUDIES.items() for e, n in d.items()])
def test_cloud_studies_are_complete_and_strict_valid(study, experiment, runs):
    folder = STUDIES / study
    if not folder.exists():
        pytest.skip(f"{study} not committed")
    audit = json.loads((folder / experiment / "validation.json").read_text(encoding="utf-8"))
    assert audit["complete"] and audit["valid_runs"] == runs and len(audit["code_revisions"]) == 1, audit["problems"][:5]
    assert not audit["code_revisions"][0].endswith("-dirty") and audit["sumo_versions"] == ["SUMO 1.28.0"]
