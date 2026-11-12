import json
import time
from types import SimpleNamespace

import pytest

from jsonbench.benchmark import supervisor


def stuck_after_start(settings, queries, path, channel):
    channel.send(time.perf_counter())
    (path / "events.jsonl").write_text('{"event": "started"}\n')
    (path / "summary.json").write_text('{}')
    time.sleep(60)


def stuck_before_start(settings, queries, path, channel):
    time.sleep(60)


def clean_exit(settings, queries, path, channel):
    channel.send(time.perf_counter())
    (path / "info.json").write_text('{"state": "complete"}')
    (path / "summary.json").write_text('{}')


def failed_exit(settings, queries, path, channel):
    raise RuntimeError("test worker failure")


def config(tmp_path):
    return SimpleNamespace(
        settings={
            "database": "mongodb", "results_directory": str(tmp_path),
            "warmup_seconds": 0, "duration": 0.01,
            "startup_timeout_seconds": 2, "drain_timeout_seconds": 0.1,
        },
        get_database_type=lambda: "mongodb",
    )


@pytest.mark.parametrize("target,reason", [
    (stuck_after_start, "drain_watchdog"),
    (stuck_before_start, "startup_watchdog"),
    (failed_exit, "worker_process_failed"),
])
def test_real_process_is_stopped_and_artifacts_marked(tmp_path, monkeypatch, target, reason):
    monkeypatch.setattr(supervisor, "_execute", target)
    start = time.perf_counter()
    with pytest.raises(RuntimeError, match=reason):
        supervisor.run_supervised(config(tmp_path), [])
    assert time.perf_counter() - start < 10
    path = next((tmp_path / "mongodb").iterdir())
    info = json.loads((path / "info.json").read_text())
    assert info["state"] == "aborted"
    assert info["abort_reason"] == reason
    assert not (path / "summary.json").exists()
    if target is stuck_after_start:
        assert json.loads((path / "events.jsonl").read_text())["event"] == "started"


def test_clean_process_retains_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(supervisor, "_execute", clean_exit)
    path = supervisor.run_supervised(config(tmp_path), [])
    assert json.loads((path / "info.json").read_text())["state"] == "complete"
    assert (path / "summary.json").exists()


def execute_with_fake_database(settings, queries, path, channel):
    from jsonbench.config_loader.config_loader import ConfigLoader

    def query(*args, **kwargs):
        time.sleep(0.002)
        return {"status": "success", "time": 0.002, "row_count": 1, "error": None}

    database = SimpleNamespace(query=query, close=lambda: None, experiment_metadata=lambda: {})
    ConfigLoader.get_database = lambda self: database
    supervisor._execute(settings, queries, path, channel)


def test_supervisor_runs_real_runner_in_spawned_process(tmp_path, monkeypatch):
    monkeypatch.setattr(supervisor, "_execute", execute_with_fake_database)
    cfg = config(tmp_path)
    cfg.settings.update(workers=2, seed=0, scale_factor=1,
                        query_selection_probability=[1], query_timeout_seconds=1,
                        drain_timeout_seconds=2)
    path = supervisor.run_supervised(
        cfg, [{"name": "Q1", "primary_collection": "x", "query": []}]
    )
    assert json.loads((path / "info.json").read_text())["state"] == "complete"
    events = [json.loads(line) for line in (path / "events.jsonl").read_text().splitlines()]
    assert {e["attempt_id"] for e in events if e["event"] == "started"} == {
        e["attempt_id"] for e in events if e["event"] == "completed"
    }
    assert json.loads((path / "summary.json").read_text())["measurement_successes"] > 0
