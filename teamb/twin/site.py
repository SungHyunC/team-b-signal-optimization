"""Online demo of the twin (GitHub Pages): recorded SUMO runs, replayed in the browser.

    python -m teamb.twin.site build             # record the demo runs, write site/
    python -m teamb.twin.site build --quick     # two short runs, while working on the player
    python -m teamb.twin.site serve             # look at site/ on http://127.0.0.1:8001
    python -m teamb.twin.site deploy            # build, then publish site/ on the gh-pages branch

GitHub Pages only serves files, so SUMO cannot run there. Each run in DEMO_RUNS is simulated
once here with the same SimEnv the live twin uses, every frame is saved, and the same web app
plays the files back (static/js/replay.js). Viewers pick a run, play, pause, change speed and
jump anywhere on the timeline. The live-only parts (Actions, AI approval, coverage and EV
switches) say that they need the local twin (`python -m teamb twin`).

site/
    index.html, static/          the web app (paths made relative, window.TWIN_STATIC set)
    data/meta.json               GET /api/meta, plus "demo": {"runs": [...], "default": {...}}
    data/geometry.json           GET /api/geometry
    data/results.json            GET /api/results (results/experiments, else docs/results/reports)
    data/runs/<id>/run.json      status, vehicle ids, all events, KPI history, the chunk list
    data/runs/<id>/NNN.json      CHUNK_S seconds of frames each (see Recording)
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import multiprocessing
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

from teamb import config
from teamb.twin import meta
from teamb.twin.server import STATIC_DIR, THREE_CDN
from teamb.twin.session import KPI_KEYS, dumps, jsonable

SITE_DIR = config.ROOT / "site"
DOCS_REPORTS = config.ROOT / "docs" / "results" / "reports"  # published copies of results/experiments
PREVIEW_IMAGE = config.ROOT / "docs" / "img" / "twin-emergency.jpg"  # link preview in chats
MARKER = ".twin-site"  # `build` only ever wipes a directory that contains this file
CHUNK_S = 300  # simulated seconds per data file: ~100 KB gzipped, fetched only when watched
SEED = 1
# Frame fields not stored like the others: t, vehicles and events go into every frame, scenario
# and controller once per run. Every other field is stored only when it changed.
PER_FRAME = ("t", "vehicles", "events", "scenario", "controller")


@dataclass(frozen=True)
class DemoRun:
    """One recorded run in the online demo."""

    scenario: str
    controller: str
    note: str  # one line shown under the run's title
    key: str = ""  # controller name in the demo UI, when params make the run a variant
    label: str = ""  # UI label for that variant
    params: dict = field(default_factory=dict)  # controller_params
    approve_after: float | None = None  # AI recommender: the engineer approves this many s after a plan appears

    @property
    def ui_controller(self) -> str:
        return self.key or self.controller

    @property
    def id(self) -> str:
        return re.sub(r"[^a-z0-9_-]+", "-", f"{self.scenario}--{self.ui_controller}")


DEMO_RUNS = [
    DemoRun("emergency", "max_pressure", "Ten ambulances and fire trucks cross the corridor; signals give them a green path."),
    DemoRun("emergency", "fixed_time", "The same emergencies with fixed-time signals (preemption still on)."),
    DemoRun("rush_hour", "fixed_time", "Baseline: the same 90 s timing every cycle, whatever the traffic."),
    DemoRun("rush_hour", "max_pressure", "Green to the axis with the biggest queue imbalance: about 59 % less delay than fixed-time in our tests."),
    DemoRun(
        "rush_hour",
        "ai_recommender",
        "The AI proposes a plan at 10:00 from navigation data; in this recording the engineer approves it a minute later.",
        params={"sync": True},
        approve_after=60,
    ),
    DemoRun("rush_hour", "rl", "Q-learning controller trained in SUMO on rush hour."),
    DemoRun("road_closure", "actuated", "A flood closes the arterial J2 → J3 at 25:00 for 30 min; traffic detours over the back street."),
    DemoRun("road_closure", "rl", "The RL controller, trained only on rush hour, struggles once the flood changes the network."),
    DemoRun("sinkhole_cross", "max_pressure", "A sinkhole cuts the cross street north of J2; turning traffic moves to J1 and J3."),
    DemoRun("earthquake", "max_pressure", "A damaged bridge and debris close two roads while seven emergency vehicles respond."),
    DemoRun("special_event", "max_pressure", "A stadium north of J3 empties onto one cross street."),
    DemoRun("fake_data_attack", "max_pressure_probe", "99 phantom phones report a jam at J2 north; a controller that trusts navigation data falls for it."),
    DemoRun(
        "fake_data_attack",
        "max_pressure_probe",
        "Same attack, but probe queues are cross-checked against the loop detectors: the fake jam is flagged and ignored.",
        key="max_pressure_probe+defense",
        label="Max-pressure on nav data + detector cross-check",
        params={"defense": True},
    ),
]
QUICK_RUNS = [DEMO_RUNS[0], DEMO_RUNS[6]]
QUICK_END = 1800.0
DEFAULT_VIEW = {"scenario": "emergency", "controller": "max_pressure", "start_at": 1170, "speed": 2}
FEATURED_REPORT = "v1-main"  # the Results tab opens on this experiment


# --- recording ----------------------------------------------------------------------
def encode_vehicles(vehicles: list, ids: dict, kinds: dict, prev: dict) -> list[int]:
    """[[id, x, y, angle, speed, kind], ...] from SimEnv.frame() -> one flat list of ints.

    x, y in decimeters, angle in whole degrees, speed in dm/s. A vehicle that was in the previous
    frame of the same chunk is [i, dx, dy, dangle, speed]; a new one is [-(i + 1), x, y, angle,
    speed, kind], where i indexes the run's vehicle ids and kind its kinds. `prev` carries the
    previous frame and is updated in place. decode_vehicles() and replay.js undo this."""
    flat, seen = [], {}
    for vid, x, y, angle, speed, kind in vehicles:
        i = ids.setdefault(vid, len(ids))
        k = kinds.setdefault(kind, len(kinds))
        X, Y, A, V = round(x * 10), round(y * 10), round(angle) % 360, round(speed * 10)
        p = prev.get(i)
        if p is not None and p[3] == k:
            flat += (i, X - p[0], Y - p[1], (A - p[2] + 180) % 360 - 180, V)
        else:
            flat += (-i - 1, X, Y, A, V, k)
        seen[i] = (X, Y, A, k)
    prev.clear()
    prev.update(seen)
    return flat


def decode_vehicles(flat: list[int], ids: list[str], kinds: list[str], prev: dict) -> list[list]:
    """Inverse of encode_vehicles (the browser does the same in replay.js)."""
    out, seen, j = [], {}, 0
    while j < len(flat):
        i = flat[j]
        if i < 0:
            i = -i - 1
            X, Y, A, V, k = flat[j + 1 : j + 6]
            j += 6
        else:
            pX, pY, pA, k = prev[i]
            dX, dY, dA, V = flat[j + 1 : j + 5]
            X, Y, A = pX + dX, pY + dY, (pA + dA) % 360
            j += 5
        seen[i] = (X, Y, A, k)
        out.append([ids[i], X / 10, Y / 10, A, V / 10, kinds[k]])
    prev.clear()
    prev.update(seen)
    return out


class Recording:
    """Writes one run's frames into chunk files of CHUNK_S simulated seconds.

    A chunk is {"t0", "frames": [...]}; each frame is {"t", "v": encode_vehicles(...), "events"
    (only when there are some), and the other SimEnv.frame() fields that changed since the
    previous frame}. The first frame of a chunk is complete, so the player can start at any chunk.
    """

    def __init__(self, folder: Path, chunk_s: float = CHUNK_S):
        self.folder = folder
        self.chunk_s = chunk_s
        self.ids: dict[str, int] = {}
        self.kinds: dict[str, int] = {}
        self.events: list[dict] = []
        self.kpi_history: list[dict] = []
        self.chunks: list[dict] = []
        self.end_t = 0.0
        self._index: int | None = None
        self._frames: list[dict] = []
        self._prev: dict = {}
        self._last: dict[str, str] = {}
        self._kpi_t = None

    def add(self, frame: dict) -> None:
        t = float(frame["t"])
        index = int(t // self.chunk_s)
        if index != self._index:
            self._flush()
            self._index = index
        out = {"t": t, "v": encode_vehicles(frame.get("vehicles") or [], self.ids, self.kinds, self._prev)}
        for key, value in frame.items():
            if key in PER_FRAME:
                continue
            value = jsonable(value)
            text = dumps(value)
            if self._last.get(key) != text:
                self._last[key] = text
                out[key] = value
        events = jsonable(frame.get("events") or [])
        if events:
            out["events"] = events
            self.events.extend(events)
        kpi = frame.get("kpi") or {}
        if kpi and kpi.get("t") != self._kpi_t:
            self._kpi_t = kpi.get("t")
            self.kpi_history.append(jsonable({k: kpi.get(k) for k in KPI_KEYS}))
        self._frames.append(out)
        self.end_t = t

    def close(self) -> None:
        self._flush()

    def _flush(self) -> None:
        if not self._frames:
            return
        name = f"{len(self.chunks):03d}.json"
        t0 = self._index * self.chunk_s
        (self.folder / name).write_text(dumps({"t0": t0, "frames": self._frames}))
        self.chunks.append({"t0": t0, "t1": self._frames[-1]["t"], "file": name, "frames": len(self._frames)})
        self._frames, self._prev, self._last = [], {}, {}


def _approve_when_due(env, delay: float, since: float | None) -> float | None:
    """Stand-in for the engineer: approve a pending AI plan `delay` seconds after it appeared."""
    rec = env.controller.pending_recommendation()
    if not rec or rec.get("status") != "pending":
        return None
    if since is None:
        return env.t
    if env.t - since >= delay:
        env.handle_command({"type": "approve", "id": rec["id"], "by": "engineer"})
        return None
    return since


def record_run(run: dict, runs_dir: str, end_time: float | None = None) -> dict:
    """Simulate one demo run and write data/runs/<id>/. Runs in a worker process."""
    from teamb.sim.env import SimEnv

    run = DemoRun(**run)
    folder = Path(runs_dir) / run.id
    folder.mkdir(parents=True, exist_ok=True)
    wall = time.time()
    with tempfile.TemporaryDirectory(prefix="teamb-site-") as tmp:
        env = SimEnv(run.scenario, run.controller, seed=SEED, controller_params=run.params or None, end_time=end_time, frames=True)
        env.output_dir = Path(tmp) / env.run_id  # the usual run files are not part of the site
        env.start()
        status = {
            "config": {
                "scenario": run.scenario,
                "controller": run.ui_controller,
                "seed": SEED,
                "coverage": env.sensors.coverage,
                "ev_preemption": env.ev_preemption,
                "sampling": env.sampling,
                "end_time": env.end_time,
                "controller_params": run.params,
                "scenario_params": {},
                "speed": DEFAULT_VIEW["speed"],
                "autoplay": True,
                "start_at": 0,
            },
            "run_id": env.run_id,
            "end_time": env.end_time,
            "warmup": env.scenario.warmup,
            "step_length": env.step_length,
            "scenario": jsonable(env.scenario.describe()),
            "controller": jsonable(env.controller.describe()),
        }
        frame_controller = env.controller.name
        rec = Recording(folder)
        rec.add(env.frame())
        pending_since = None
        while not env.finished:
            env.step()
            if run.approve_after is not None:
                pending_since = _approve_when_due(env, run.approve_after, pending_since)
            rec.add(env.frame())
        status["summary"] = jsonable(env.close())
    rec.close()
    info = {
        "id": run.id,
        "scenario": run.scenario,
        "controller": run.ui_controller,
        "frame_controller": frame_controller,
        "note": run.note,
        "status": status,
        "ids": list(rec.ids),
        "kinds": list(rec.kinds),
        "events": rec.events,
        "kpi_history": rec.kpi_history,
        "chunk_s": CHUNK_S,
        "chunks": rec.chunks,
        "end_t": rec.end_t,
        "recorded": time.strftime("%Y-%m-%d"),
    }
    (folder / "run.json").write_text(dumps(info))
    size = sum(p.stat().st_size for p in folder.iterdir())
    return {"id": run.id, "frames": sum(c["frames"] for c in rec.chunks), "mb": size / 1e6, "wall_s": time.time() - wall}


# --- the site ------------------------------------------------------------------------
def github_urls(remote: str) -> tuple[str, str] | None:
    """'https://github.com/Owner/repo.git' (or git@github.com:Owner/repo) -> (repo URL, Pages URL)."""
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", remote.strip())
    if not m:
        return None
    owner, repo = m.groups()
    return f"https://github.com/{owner}/{repo}", f"https://{owner.lower()}.github.io/{repo}/"


def _git(*args: str, cwd: Path = config.ROOT, env: dict | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()


def _remote_urls() -> tuple[str, str] | None:
    try:
        return github_urls(_git("remote", "get-url", "origin"))
    except (OSError, subprocess.CalledProcessError):
        return None


def index_html(repo_url: str | None, pages_url: str | None) -> str:
    """static/index.html with relative paths, three.js from the pinned CDN, the static flag and
    a link preview (Discord, Slack and KakaoTalk show it when the URL is pasted)."""
    html = (STATIC_DIR / "index.html").read_text()
    swaps = [('href="/static/', 'href="static/'), ('src="/static/', 'src="static/'), ('"/vendor/three/', f'"{THREE_CDN}')]
    for old, new in swaps:
        if old not in html:
            raise RuntimeError(f"static/index.html no longer contains {old!r}: update teamb/twin/site.py")
        html = html.replace(old, new)
    flag = {"data": "data/", "repo": repo_url, "built": time.strftime("%Y-%m-%d")}
    html = html.replace('<script type="module"', f"<script>window.TWIN_STATIC = {json.dumps(flag)};</script>\n  <script type=\"module\"", 1)
    description = (
        "Team B's SUMO digital twin of a four-junction corridor: AI signal control, ambulances, floods "
        "and a fake-navigation-data attack, recorded and replayed in your browser."
    )
    tags = [
        f'<meta name="description" content="{description}">',
        '<meta property="og:title" content="Signal Twin · Team B">',
        f'<meta property="og:description" content="{description}">',
        '<meta property="og:type" content="website">',
    ]
    if pages_url:
        tags += [
            f'<meta property="og:url" content="{pages_url}">',
            f'<meta property="og:image" content="{pages_url}preview.jpg">',
            '<meta name="twitter:card" content="summary_large_image">',
        ]
    return html.replace("</title>", "</title>\n  " + "\n  ".join(tags), 1)


def reports() -> list[dict]:
    """Experiment reports for the Results tab: local results/experiments, else the published
    copies in docs/results/reports (the numbers quoted in docs/results/)."""
    merged = {r["dir"]: r for r in meta.list_reports(DOCS_REPORTS)}
    merged.update({r["dir"]: r for r in meta.list_reports(config.RESULTS / "experiments")})
    found = sorted(merged.values(), key=lambda r: (str(r.get("created") or ""), r["modified_unix"]), reverse=True)
    return sorted(found, key=lambda r: r["dir"] != FEATURED_REPORT)  # stable: the rest keep their order


def demo_meta(runs: list[DemoRun], recorded: dict[str, dict]) -> dict:
    """GET /api/meta plus the recorded runs. A variant (e.g. with the detector cross-check)
    becomes its own controller entry so the run picker and titles can name it."""
    data = meta.build_meta()
    known = {c["name"]: c for c in data["controllers"]}
    for run in runs:
        if run.key and run.key not in known:
            base = dict(known.get(run.controller, {"name": run.controller}))
            base.update(name=run.key, label=run.label or run.key, params=run.params)
            data["controllers"].append(base)
            known[run.key] = base
    present = [r for r in runs if r.id in recorded]
    default = next((r for r in present if r.scenario == DEFAULT_VIEW["scenario"] and r.controller == DEFAULT_VIEW["controller"]), None)
    data["demo"] = {
        "runs": [{"id": r.id, "scenario": r.scenario, "controller": r.ui_controller, "note": r.note, **recorded[r.id]} for r in present],
        "default": DEFAULT_VIEW if default else {"scenario": present[0].scenario, "controller": present[0].ui_controller, "start_at": 240, "speed": 2},
    }
    return jsonable(data)


def _clean(out: Path) -> None:
    if out.exists():
        if not (out / MARKER).exists() and any(out.iterdir()):
            raise SystemExit(f"{out} exists and was not made by this script; pass another --out")
        shutil.rmtree(out)


def build(out: Path = SITE_DIR, runs: list[DemoRun] | None = None, end_time: float | None = None, jobs: int | None = None) -> Path:
    runs = DEMO_RUNS if runs is None else runs
    out = Path(out)
    _clean(out)
    runs_dir = out / "data" / "runs"
    runs_dir.mkdir(parents=True)
    (out / MARKER).write_text("made by python -m teamb.twin.site build; safe to delete\n")
    meta.geometry()  # build the network once here, not in every worker at the same time

    workers = max(1, min(jobs or (os.cpu_count() or 2) - 1, len(runs), 6))
    print(f"recording {len(runs)} run(s) with {workers} worker(s)…", flush=True)
    recorded: dict[str, dict] = {}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
        futures = {pool.submit(record_run, asdict(run), str(runs_dir), end_time): run for run in runs}
        for fut in as_completed(futures):
            res = fut.result()
            recorded[res["id"]] = {"frames": res["frames"], "mb": round(res["mb"], 2)}
            print(f"  {res['id']:45s} {res['frames']:5d} frames  {res['mb']:5.1f} MB  {res['wall_s']:5.0f} s", flush=True)

    shutil.copytree(STATIC_DIR, out / "static", ignore=shutil.ignore_patterns("vendor", ".DS_Store"))
    urls = _remote_urls()
    repo_url, pages_url = urls if urls else (None, None)
    (out / "index.html").write_text(index_html(repo_url, pages_url))
    if PREVIEW_IMAGE.exists():
        shutil.copyfile(PREVIEW_IMAGE, out / "preview.jpg")
    data = out / "data"
    (data / "meta.json").write_text(dumps(demo_meta(runs, recorded)))
    (data / "geometry.json").write_text(meta.geometry_json())
    found = reports()
    (data / "results.json").write_text(dumps(found))
    (out / ".nojekyll").touch()  # serve the files as they are (no Jekyll build on GitHub Pages)
    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"site written to {out} ({total / 1e6:.1f} MB, {len(found)} result report(s), {time.time() - t0:.0f} s)")
    if not found:
        print("note: no experiment reports found, so the Results tab will be empty (see docs/results/)")
    return out


def serve(out: Path = SITE_DIR, port: int = 8001) -> None:
    if not (out / "index.html").exists():
        raise SystemExit(f"nothing to serve in {out}: run `python -m teamb.twin.site build` first")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
    print(f"\n  Team B signal twin, online demo  ->  http://127.0.0.1:{port}\n", flush=True)
    http.server.ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()


def deploy(out: Path = SITE_DIR, branch: str = "gh-pages", message: str | None = None) -> None:
    """Publish `out` as the single commit of `branch` on origin. Force-pushed on purpose: old
    recordings are replaced instead of piling up in the history."""
    if not (out / "index.html").exists():
        raise SystemExit(f"nothing to deploy in {out}: run `python -m teamb.twin.site build` first")
    remote = _git("remote", "get-url", "origin")
    head = _git("rev-parse", "--short", "HEAD")
    dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    message = message or f"Online demo built from {head}{' with local changes' if dirty else ''}"
    with tempfile.TemporaryDirectory(prefix="teamb-pages-") as tmp:
        env = {**os.environ, "GIT_DIR": str(Path(tmp) / "git"), "GIT_WORK_TREE": str(out)}
        _git("init", "--quiet", "--initial-branch", branch, env=env)
        _git("add", "--all", env=env)
        _git("commit", "--quiet", "--message", message, env=env)
        subprocess.run(["git", "push", "--force", remote, f"HEAD:refs/heads/{branch}"], cwd=config.ROOT, env=env, check=True)
    urls = github_urls(remote)
    if urls:
        _enable_pages(urls[0].removeprefix("https://github.com/"), branch)
        print(f"\npublished: {urls[1]}  (GitHub Pages needs a minute or two to update)")


def _enable_pages(repo: str, branch: str) -> None:
    """Turn GitHub Pages on for `branch` if it is off. Needs the gh CLI and admin rights on the
    repo; anyone else gets the one-time manual step instead."""
    hint = f"enable it once: GitHub → {repo} → Settings → Pages → Deploy from a branch → {branch} / (root)"
    if not shutil.which("gh"):
        print(f"note: could not check GitHub Pages (no gh CLI); if the site does not appear, {hint}")
        return
    if subprocess.run(["gh", "api", f"repos/{repo}/pages"], capture_output=True).returncode == 0:
        return
    r = subprocess.run(
        ["gh", "api", "-X", "POST", f"repos/{repo}/pages", "-f", f"source[branch]={branch}", "-f", "source[path]=/"],
        capture_output=True,
        text=True,
    )
    print("GitHub Pages enabled" if r.returncode == 0 else f"note: could not enable GitHub Pages ({r.stderr.strip()}); {hint}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m teamb.twin.site", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "deploy"):
        p = sub.add_parser(name, help="record the demo runs and write the site" if name == "build" else "build, then publish on gh-pages")
        p.add_argument("--out", type=Path, default=SITE_DIR)
        p.add_argument("--quick", action="store_true", help=f"only {len(QUICK_RUNS)} runs, {QUICK_END:.0f} s each")
        p.add_argument("--jobs", type=int, help="parallel SUMO runs (default: CPU count - 1, at most 6)")
    deploy_p = sub.choices["deploy"]
    deploy_p.add_argument("--no-build", action="store_true", help="publish the existing --out as it is")
    deploy_p.add_argument("--branch", default="gh-pages")
    deploy_p.add_argument("--message", help="commit message on the gh-pages branch")
    serve_p = sub.add_parser("serve", help="serve the built site locally")
    serve_p.add_argument("--out", type=Path, default=SITE_DIR)
    serve_p.add_argument("--port", type=int, default=8001)
    args = parser.parse_args(argv)

    if args.command == "serve":
        serve(args.out, args.port)
        return 0
    if args.command == "build" or not args.no_build:
        if args.quick:
            build(args.out, QUICK_RUNS, end_time=QUICK_END, jobs=args.jobs)
        else:
            build(args.out, jobs=args.jobs)
    if args.command == "deploy":
        deploy(args.out, args.branch, args.message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
