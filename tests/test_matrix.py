import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from jsonbench import matrix

MANIFEST = json.loads(Path("experiments/paper-matrix.json").read_text())


def test_paper_matrix_has_three_repetitions_and_reversed_second_order():
    cells = matrix.expand(MANIFEST)
    assert len(cells) == 108
    assert len({c["id"] for c in cells}) == 108
    assert [c["workers"] for c in cells[:12]] == [2, 4, 8, 16, 32, 64, 64, 32, 16, 8, 4, 2]
    assert all(c["backend"] == "mongodb" for c in cells[:54])


def test_lock_prevents_second_runner(tmp_path):
    with matrix.locked(tmp_path), pytest.raises(RuntimeError, match="Another"):
        with matrix.locked(tmp_path):
            pass


def test_changed_plan_refused(tmp_path):
    matrix.plan("experiments/paper-matrix.json", tmp_path)
    path = tmp_path / "plan.json"
    data = json.loads(path.read_text())
    data["revision"] = "different"
    matrix.atomic_json(path, data)
    with pytest.raises(ValueError, match="changed"):
        matrix.plan("experiments/paper-matrix.json", tmp_path)


def test_resume_skips_complete_preserves_failed_attempt(tmp_path, monkeypatch):
    manifest = {**MANIFEST, "cooldown_seconds": 0}
    cells = matrix.expand(manifest)[:2]
    monkeypatch.setattr(matrix, "ensure_other_database_stopped", lambda _: None)
    database = SimpleNamespace(server_version=lambda: "8.2.1")
    monkeypatch.setattr(
        matrix,
        "make_config",
        lambda *a: SimpleNamespace(settings={}, get_database=lambda: database, close=lambda: None),
    )
    loads = []
    monkeypatch.setattr(matrix, "load_dataset", lambda _: loads.append(1))
    monkeypatch.setattr(matrix, "generate_queries", lambda _: [])
    calls = []

    def execute(config, queries):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("infrastructure failure")
        path = Path(config.settings["results_directory"]) / "mongodb" / "run"
        path.mkdir(parents=True)
        (path / "info.json").write_text('{"state":"complete"}')
        (path / "summary.json").write_text("{}")
        return path

    monkeypatch.setattr(matrix, "run_supervised", execute)
    args = (manifest, Path("unused"), cells, tmp_path, "mongodb", {"mongodb": {}})
    with pytest.raises(RuntimeError, match="infrastructure"):
        matrix.run(*args)
    with pytest.raises(RuntimeError, match="retry-failed"):
        matrix.run(*args)
    matrix.run(*args, retry_failed=True)
    state = json.loads((tmp_path / "state.json").read_text())
    assert len(calls) == 3
    assert len(state["attempts"][cells[0]["id"]]) == 1
    assert [a["state"] for a in state["attempts"][cells[1]["id"]]] == ["failed", "complete"]
    assert len(loads) == 2


def test_dataset_manifest_changes_are_not_silently_adopted(tmp_path, monkeypatch):
    manifest = {**MANIFEST, "scale_factors": [10]}
    path = matrix.dataset_path(tmp_path, 10)
    path.mkdir(parents=True)
    data = {"seed": 42, "scale_factor": 10, "reference_date": "2025-11-01"}
    (path / "manifest.json").write_text(json.dumps(data))
    monkeypatch.setattr(matrix, "validate_dataset", lambda _: data)
    matrix.prepare(manifest, tmp_path)
    (path / "manifest.json").write_text(json.dumps({**data, "extra": "changed"}))
    with pytest.raises(ValueError, match="manifests changed"):
        matrix.prepare(manifest, tmp_path)


def test_active_other_database_refuses_execution(monkeypatch):
    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(matrix.socket, "create_connection", lambda *a, **k: Socket())
    with pytest.raises(RuntimeError, match="Other database"):
        matrix.ensure_other_database_stopped("mongodb")
