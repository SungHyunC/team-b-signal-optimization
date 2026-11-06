"""teamb exp run --backend modal glue (teamb.experiments.cloud.run_specs) with a fake Modal function.

No network: checks resume rules (same as local runs), archive unpacking and lost runs.
"""
from __future__ import annotations

import contextlib
import io
import json
import tarfile
import types
from dataclasses import asdict

import pytest

cloud = pytest.importorskip("teamb.experiments.cloud")
from teamb.experiments.runner import RunSpec  # noqa: E402


def _archive(name: str, files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f"{name}/{rel}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class FakeRemote:
    def __init__(self, lose=()):
        self.sent, self.lose, self.options = [], set(lose), {}

    def with_options(self, **options):
        self.options = options
        return self

    def map(self, specs, kwargs=None, order_outputs=True, return_exceptions=False):
        for spec in specs:
            name = RunSpec(**spec).name
            self.sent.append(name)
            if name in self.lose:
                yield RuntimeError("container preempted")
                continue
            summary = {"mean_delay_s": 1.0, "complete": True, "end_time": spec["end_time"], "sim_time_s": spec["end_time"]}
            files = {"summary.json": json.dumps(summary), "run_spec.json": json.dumps({**spec, "name": name})}
            yield {"run": name, "status": "ok", "summary": summary, "archive": _archive(name, files)}


@pytest.fixture
def fake(monkeypatch):
    if cloud.modal is None:
        pytest.skip("modal is not installed")
    monkeypatch.setattr(cloud, "app", types.SimpleNamespace(run=contextlib.nullcontext))
    monkeypatch.setattr(cloud.modal, "enable_output", contextlib.nullcontext)

    def install(remote):
        monkeypatch.setattr(cloud, "run_remote", remote)
        return remote
    return install


def _specs():
    return [RunSpec("rush_hour", c, 1, 1.0, end_time=1500.0) for c in ("fixed_time", "max_pressure")]


def test_runs_execute_remotely_and_unpack_into_the_runs_folder(fake, tmp_path):
    remote = fake(FakeRemote())
    results = list(cloud.run_specs(_specs(), tmp_path, workers=3, git_revision="abc"))
    assert remote.options == {"max_containers": 3}
    assert sorted(r["status"] for r in results) == ["ok", "ok"]
    for spec in _specs():
        assert json.loads((tmp_path / spec.name / "summary.json").read_text())["complete"] is True


def test_resume_reuses_only_complete_runs_like_the_local_backend(fake, tmp_path):
    fake(FakeRemote())
    list(cloud.run_specs(_specs(), tmp_path, workers=2))
    done, broken = _specs()
    (tmp_path / broken.name / "summary.json").unlink()  # e.g. interrupted before the summary was written
    remote = fake(FakeRemote())
    results = {r["run"]: r for r in cloud.run_specs(_specs(), tmp_path, workers=2)}
    assert remote.sent == [broken.name]
    assert results[done.name]["status"] == "skipped"
    assert results[broken.name]["status"] == "ok"


def test_a_lost_container_is_reported_by_run_name(fake, tmp_path):
    lost = _specs()[1].name
    fake(FakeRemote(lose={lost}))
    results = {r["run"]: r for r in cloud.run_specs(_specs(), tmp_path, workers=2)}
    assert results[lost]["status"] == "failed" and "container preempted" in results[lost]["error"]


def test_archives_cannot_write_outside_their_run_folder(tmp_path):
    evil = _archive("../escape", {"x.txt": "nope"})
    with pytest.raises(ValueError):
        cloud._safe_extract(evil, tmp_path / "runs", "run_a")
    assert not (tmp_path / "escape").exists()


class FlakyRemote(FakeRemote):
    """The first map() dies after one result, like a dropped gRPC stream."""

    def __init__(self):
        super().__init__()
        self.maps = 0

    def map(self, specs, kwargs=None, order_outputs=True, return_exceptions=False):
        self.maps += 1
        for i, item in enumerate(super().map(specs, kwargs, order_outputs, return_exceptions)):
            if self.maps == 1 and i == 1:
                raise ConnectionError("Connection lost")
            yield item


def test_a_dropped_client_connection_retries_only_the_missing_runs(fake, tmp_path):
    remote = fake(FlakyRemote())
    results = list(cloud.run_specs(_specs(), tmp_path, workers=2))
    assert remote.maps == 2
    assert sorted(r["status"] for r in results) == ["ok", "ok"]
    assert remote.sent == [_specs()[0].name, _specs()[1].name, _specs()[1].name]
