"""Documentation stays navigable and honest.

- Every relative link in a tracked Markdown file points at a file or folder that exists.
- Documented `teamb exp run` / `python -m teamb.experiments run` commands still pass --dry-run
  (put `<!-- docs-check: skip -->` on the line before a fenced block that must not be checked,
  e.g. a command that needs another branch).
- The cloud deployment guide documents every TWIN_* switch and matches render.yaml.
"""
from __future__ import annotations

import contextlib
import io
import re
import shlex
import subprocess
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
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


def _experiment_commands():
    """`... experiments run ...` commands in fenced bash/sh/console blocks of the docs."""
    for md in MARKDOWN:
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
