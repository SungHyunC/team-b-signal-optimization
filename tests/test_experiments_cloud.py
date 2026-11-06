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


class FakeCall:
    def __init__(self, result=None, error=None, flaky=0):
        self.result, self.error, self.flaky = result, error, flaky

    def get(self, timeout=None):
        if self.flaky:  # a dropped client connection while waiting
            self.flaky -= 1
            raise ConnectionError("Connection lost")
        if self.error:
            raise self.error
        return dict(self.result)


class FakeRemote:
    def __init__(self, lose=(), lose_once=(), flaky=0):
        self.sent, self.lose, self.lose_once, self.flaky, self.options = [], set(lose), set(lose_once), flaky, {}

    def with_options(self, **options):
        self.options = options
        return self

    def spawn(self, spec, git_revision):
        name = RunSpec(**spec).name
        self.sent.append(name)
        if name in self.lose or name in self.lose_once:
            self.lose_once.discard(name)
            return FakeCall(error=RuntimeError("container preempted"))
        summary = {"mean_delay_s": 1.0, "complete": True, "end_time": spec["end_time"], "sim_time_s": spec["end_time"]}
        files = {"summary.json": json.dumps(summary), "run_spec.json": json.dumps({**spec, "name": name})}
        return FakeCall({"run": name, "status": "ok", "summary": summary, "archive": _archive(name, files)}, flaky=self.flaky)


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


def test_a_dropped_client_connection_only_interrupts_the_wait(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(cloud.time, "sleep", lambda s: None)
    remote = fake(FakeRemote(flaky=2))
    results = list(cloud.run_specs(_specs(), tmp_path, workers=2))
    assert sorted(r["status"] for r in results) == ["ok", "ok"]
    assert sorted(remote.sent) == sorted(s.name for s in _specs()), "nothing re-submitted"


def test_a_run_lost_on_modal_is_resubmitted(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(cloud.time, "sleep", lambda s: None)
    lost = _specs()[1].name
    remote = fake(FakeRemote(lose_once={lost}))
    results = {r["run"]: r for r in cloud.run_specs(_specs(), tmp_path, workers=2)}
    assert results[lost]["status"] == "ok"
    assert remote.sent.count(lost) == 2


class Spinning(BaseException):
    """A FakeCall polled far more often than any real wait needs: _collect is looping."""


class StickyCall(FakeCall):
    """get() raises the same stored error every time, like a finished Modal call; bounded."""

    def __init__(self, error, limit=50):
        super().__init__(error=error)
        self.calls, self.limit = 0, limit

    def get(self, timeout=None):
        self.calls += 1
        if self.calls > self.limit:
            raise Spinning(f"get() called {self.calls} times")
        return super().get(timeout)


class ErrorRemote(FakeRemote):
    """FakeRemote whose calls for `names` fail with `make_error()` on every get()."""

    def __init__(self, names, make_error):
        super().__init__()
        self.names, self.make_error = set(names), make_error

    def spawn(self, spec, git_revision):
        call = super().spawn(spec, git_revision)
        return StickyCall(self.make_error()) if RunSpec(**spec).name in self.names else call


def test_a_run_past_the_modal_function_timeout_fails_without_resubmitting(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(cloud.time, "sleep", lambda s: None)
    slow = _specs()[1].name
    remote = fake(ErrorRemote({slow}, lambda: cloud.modal.exception.FunctionTimeoutError("function timed out")))
    results = {r["run"]: r for r in cloud.run_specs(_specs(), tmp_path, workers=2)}
    assert results[slow]["status"] == "failed" and "FunctionTimeoutError" in results[slow]["error"]
    assert remote.sent.count(slow) == 1, "a deterministic timeout is not worth another hour"
    assert results[_specs()[0].name]["status"] == "ok"


def test_an_expired_output_is_resubmitted_then_reported(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(cloud.time, "sleep", lambda s: None)
    gone = _specs()[1].name
    remote = fake(ErrorRemote({gone}, lambda: cloud.modal.exception.OutputExpiredError("output expired")))
    results = {r["run"]: r for r in cloud.run_specs(_specs(), tmp_path, workers=2)}
    assert results[gone]["status"] == "failed" and "OutputExpiredError" in results[gone]["error"]
    assert remote.sent.count(gone) == cloud.CLIENT_ATTEMPTS


def test_the_poll_timeout_only_means_still_running(fake, tmp_path):
    class SlowCall(FakeCall):
        def __init__(self, inner, polls):
            super().__init__(inner.result)
            self.polls = polls

        def get(self, timeout=None):
            if self.polls:
                self.polls -= 1
                raise TimeoutError()  # what FunctionCall.get(timeout=...) raises while the run is going
            return super().get(timeout)

    class SlowRemote(FakeRemote):
        def spawn(self, spec, git_revision):
            return SlowCall(super().spawn(spec, git_revision), polls=3)

    remote = fake(SlowRemote())
    results = list(cloud.run_specs(_specs(), tmp_path, workers=2))
    assert sorted(r["status"] for r in results) == ["ok", "ok"]
    assert sorted(remote.sent) == sorted(s.name for s in _specs()), "nothing re-submitted"


def test_archives_cannot_write_into_a_sibling_run_folder(tmp_path):
    sibling = _archive("run_a_evil", {"summary.json": "{}"})  # shares the prefix "run_a"
    with pytest.raises(ValueError):
        cloud._safe_extract(sibling, tmp_path / "runs", "run_a")
    assert not (tmp_path / "runs" / "run_a_evil").exists()


def test_a_result_for_another_run_name_is_not_unpacked(fake, tmp_path):
    victim = tmp_path / "keep_me"
    victim.mkdir()

    class Liar(FakeRemote):
        def spawn(self, spec, git_revision):
            call = super().spawn(spec, git_revision)
            call.result = {**call.result, "run": "../keep_me"}
            return call

    fake(Liar())
    results = list(cloud.run_specs(_specs(), tmp_path / "runs", workers=2))
    assert victim.is_dir(), "a result naming another folder must not delete it"
    assert [r["status"] for r in results] == ["failed", "failed"]
    assert all(r["run"] in {s.name for s in _specs()} and "expected" in r["error"] for r in results)
