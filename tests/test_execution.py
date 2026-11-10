import json
from types import SimpleNamespace

import pytest

from jsonbench.benchmark.benchmark import (
    summarize_events,
    validate_probabilities,
    worker_loop,
)
from jsonbench.config_loader.config_loader import ConfigLoader
from jsonbench.database_connectors.outcome import consume


def test_consumption_includes_later_batches_and_closes():
    state = {"time": 0, "closed": False}

    class Cursor:
        def __iter__(self):
            for _ in range(3):
                state["time"] += 2
                yield {}

        def close(self):
            state["closed"] = True

    result = consume(
        Cursor, errors=(TimeoutError,), is_timeout=lambda e: True, clock=lambda: state["time"]
    )
    assert result["time"] == 6
    assert result["row_count"] == 3
    assert result["status"] == "success"
    assert state["closed"]


def test_timeout_during_consumption_preserves_duration():
    ticks = iter([0, 12])

    def rows():
        yield {}
        raise TimeoutError("late batch")

    result = consume(
        rows, errors=(TimeoutError,), is_timeout=lambda e: True, clock=lambda: next(ticks)
    )
    assert result["status"] == "timeout"
    assert result["time"] == 12
    assert result["row_count"] is None
    assert result["error"]["type"] == "TimeoutError"


def test_programming_errors_propagate():
    def broken():
        raise TypeError("bug")

    with pytest.raises(TypeError):
        consume(broken, errors=(TimeoutError,), is_timeout=lambda e: True)


def test_worker_stops_admissions_but_records_late_finish():
    now = [0]
    events = []

    def query(*args, **kwargs):
        assert kwargs["timeout_seconds"] == 5
        now[0] += 4
        return {"status": "success", "time": 4, "row_count": 1, "error": None}

    worker_loop(
        SimpleNamespace(query=query),
        [{"name": "Q1", "primary_collection": "x", "query": []}],
        [1],
        worker=0,
        seed=1,
        origin=0,
        warmup=2,
        duration=8,
        timeout=5,
        emit=events.append,
        clock=lambda: now[0],
    )
    done = [r for r in events if r["event"] == "completed"]
    assert [r["start_seconds"] for r in done] == [0, 4, 8]
    assert done[-1]["finish_seconds"] == 12
    summary = summarize_events(events, 2, 8)
    assert summary["successful_completion_throughput_qps"] == 2 / 8
    assert summary["measurement_success_mean_seconds"] == 4
    assert summary["measurement_attempts_completed"] == 2
    assert summary["late_completions"] == 1


def test_failures_and_end_boundary_not_successful_throughput():
    events = [
        {"event": "completed", "status": s, "start_seconds": 1, "finish_seconds": f, "time": f - 1}
        for s, f in [("timeout", 2), ("error", 3), ("success", 10)]
    ]
    result = summarize_events(events, 0, 10)
    assert result["successful_completion_throughput_qps"] == 0
    assert result["measurement_timeouts"] == result["measurement_errors"] == 1
    assert result["measurement_success_mean_seconds"] == 9


@pytest.mark.parametrize("probabilities", [[], [0], [-1], [float("nan")], [True], [0.5]])
def test_invalid_selection(probabilities):
    with pytest.raises(ValueError):
        validate_probabilities([{}], probabilities)


def test_configuration_does_not_connect(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"database": "mongodb", "workers": 2}))
    config = ConfigLoader(path)
    assert config.database is None
    assert config.settings["warmup_seconds"] == 60
    config.close()


def test_mongo_connector_returns_consumed_outcome():
    from jsonbench.database_connectors.mongodb import MongoDB

    connector = MongoDB.__new__(MongoDB)
    seen = []

    def rows():
        for i in range(3):
            seen.append(i)
            yield {"x": i}

    connector.database = {"x": SimpleNamespace(aggregate=lambda query: rows())}
    result = connector.query("x", [], timeout_seconds=1)
    assert result["status"] == "success"
    assert result["row_count"] == 3
    assert seen == [0, 1, 2]


def test_couchbase_connector_preserves_database_timeout():
    from couchbase.exceptions import UnAmbiguousTimeoutException

    from jsonbench.database_connectors.couchbase import Couchbase

    connector = Couchbase.__new__(Couchbase)

    def query(*args):
        raise UnAmbiguousTimeoutException("test timeout")

    connector.cb_scope = SimpleNamespace(query=query)
    result = connector.query("x", "SELECT 1", timeout_seconds=1)
    assert result["status"] == "timeout"
    assert result["time"] >= 0
    assert result["error"]["type"] == "UnAmbiguousTimeoutException"


def test_runner_persists_shared_timeline_and_unique_runs(tmp_path):
    import time

    from jsonbench.benchmark.benchmark import main

    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "database": "mongodb",
                "workers": 2,
                "duration": 0.02,
                "warmup_seconds": 0,
                "query_timeout_seconds": 1,
                "scale_factor": 1,
                "query_selection_probability": [1],
                "results_directory": str(tmp_path / "results"),
            }
        )
    )
    config = ConfigLoader(path)

    def query(*args, **kwargs):
        time.sleep(0.002)
        return {"status": "success", "time": 0.002, "row_count": 1, "error": None}

    config.database = SimpleNamespace(query=query)
    queries = [{"name": "Q1", "primary_collection": "x", "query": []}]
    first = main(config, queries)
    second = main(config, queries)
    assert first != second
    info = json.loads((first / "info.json").read_text())
    events = [json.loads(line) for line in (first / "events.jsonl").read_text().splitlines()]
    assert info["state"] == "complete"
    starts = {e["attempt_id"] for e in events if e["event"] == "started"}
    finishes = {e["attempt_id"] for e in events if e["event"] == "completed"}
    assert starts == finishes
    assert {e["worker"] for e in events} == {0, 1}
    assert all(e["start_seconds"] < 0.02 for e in events)


def test_runner_failure_keeps_started_event_and_marks_aborted(tmp_path):
    from jsonbench.benchmark.benchmark import main

    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "database": "mongodb",
                "workers": 1,
                "duration": 0.02,
                "warmup_seconds": 0,
                "scale_factor": 1,
                "query_selection_probability": [1],
                "results_directory": str(tmp_path / "results"),
            }
        )
    )
    config = ConfigLoader(path)

    def query(*args, **kwargs):
        raise TypeError("programming defect")

    config.database = SimpleNamespace(query=query)
    with pytest.raises(TypeError):
        main(config, [{"name": "Q1", "primary_collection": "x", "query": []}])
    run = next((tmp_path / "results/mongodb").iterdir())
    assert json.loads((run / "info.json").read_text())["state"] == "aborted"
    assert json.loads((run / "events.jsonl").read_text())["event"] == "started"


def test_couchbase_index_creation_waits_for_readiness():
    from jsonbench.database_connectors.couchbase import Couchbase

    connector = Couchbase.__new__(Couchbase)
    executed, watched = [], []

    def query(sql):
        return SimpleNamespace(execute=lambda: executed.append(sql))

    def collection(name):
        return SimpleNamespace(
            query_indexes=lambda: SimpleNamespace(
                watch_indexes=lambda names, **kw: watched.append((name, names, kw["timeout"]))
            )
        )

    connector.cb_scope = SimpleNamespace(query=query, collection=collection)
    connector.create_indexes()
    assert len(executed) == len(watched) == 3
    assert watched[1][0:2] == ("bookings", ["bookings-tour_id"])
    assert all(timeout.total_seconds() == 300 for _, _, timeout in watched)
