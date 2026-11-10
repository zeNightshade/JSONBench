import json

import pytest

from jsonbench.analysis import summarize_records, summarize_run


def test_parallel_queries_keep_individual_latency():
    result = summarize_records([{"time": 10}] * 4)
    assert result["mean_seconds"] == 10
    assert result["throughput_qps"] is None


def test_nulls_are_not_zero_or_success():
    result = summarize_records([{"time": 10}, {"time": None}, {"time": 20}])
    assert result["mean_seconds"] == 15
    assert result["numeric_timings"] == 2
    assert result["missing_timings"] == 1


@pytest.mark.parametrize("records", [[], [{"time": None}] * 320])
def test_no_measurements_is_undefined(records):
    assert summarize_records(records)["mean_seconds"] is None


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True, "10"])
def test_invalid_timing_rejected(value):
    with pytest.raises((ValueError, TypeError)):
        summarize_records([{"time": value}])


def write_run(path, observations, workers=1):
    path.mkdir()
    (path / "info.json").write_text(json.dumps({"workers": workers, "duration": 300}))
    (path / "results.json").write_text(json.dumps(observations))


def test_independent_query_aggregation(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_run(a, [[{"name": "Q1", "time": 1}, {"name": "Q1", "time": 3}]])
    write_run(b, [[{"name": "Q1", "time": 100}] * 5])
    assert summarize_run(a)["queries"]["Q1"]["mean_seconds"] == 2
    assert summarize_run(b)["queries"]["Q1"]["mean_seconds"] == 100
    assert summarize_run(a)["configured_duration_seconds"] == 300


def test_worker_mismatch_rejected(tmp_path):
    write_run(tmp_path / "run", [[]], workers=2)
    with pytest.raises(ValueError, match="Worker metadata"):
        summarize_run(tmp_path / "run")


def test_manifest_mismatch_rejected(tmp_path):
    write_run(tmp_path / "run", [[]])
    with pytest.raises(ValueError, match="Selected concurrency"):
        summarize_run(tmp_path / "run", expected_workers=4)
