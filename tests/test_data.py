import json
from types import SimpleNamespace

import pytest

from jsonbench.data_generator.data_generator import generate_dataset, load_dataset


def test_deterministic_data_and_references(tmp_path):
    args = {"scale": 0.01, "seed": 23, "reference_date": "2025-11-01"}
    first = generate_dataset(tmp_path / "a", **args)
    second = generate_dataset(tmp_path / "b", **args)
    assert first == second
    assert {k: v["count"] for k, v in first["collections"].items()} == {
        "users": 10,
        "tours": 2,
        "bookings": 50,
        "reviews": 25,
    }
    data = {
        c: [json.loads(line) for line in (tmp_path / "a" / f"{c}.jsonl").read_text().splitlines()]
        for c in first["collections"]
    }
    bookings = {d["_id"]: d for d in data["bookings"]}
    for review in data["reviews"]:
        booking = bookings[review["booking_id"]]
        assert review["tour_id"] == booking["tour_id"]
        assert booking["date"] < review["date"] <= args["reference_date"]
    changed = generate_dataset(tmp_path / "c", **{**args, "seed": 24})
    assert first["collections"] != changed["collections"]


def test_corrupt_data_rejected_before_connection(tmp_path):
    generate_dataset(tmp_path / "a", scale=0.01, seed=0, reference_date="2025-11-01")
    (tmp_path / "a/users.jsonl").write_text("corrupt")
    config = SimpleNamespace(
        settings={"dataset_directory": str(tmp_path / "a"), "replace_collections": True}
    )
    with pytest.raises(ValueError, match="checksum"):
        load_dataset(config)


def test_loading_requires_explicit_replacement(tmp_path):
    generate_dataset(tmp_path / "a", scale=0.01, seed=0, reference_date="2025-11-01")
    config = SimpleNamespace(settings={"dataset_directory": str(tmp_path / "a")})
    with pytest.raises(ValueError, match="replace_collections"):
        load_dataset(config)


@pytest.mark.parametrize("defect", ["missing", "version", "count", "bytes", "duplicate", "json", "id", "nan"])
def test_invalid_artifacts_never_connect(tmp_path, defect):
    import hashlib

    path = tmp_path / "dataset"
    manifest = generate_dataset(path, scale=0.01, seed=0, reference_date="2025-11-01")
    file = path / "users.jsonl"
    if defect == "missing":
        del manifest["collections"]["reviews"]
    elif defect == "version":
        manifest["format_version"] = 2
    elif defect in {"count", "bytes"}:
        manifest["collections"]["users"][defect] += 1
    else:
        lines = file.read_text().splitlines()
        lines[1] = {
            "duplicate": lines[0],
            "json": "{broken",
            "id": '{"_id": 42}',
            "nan": '{"_id": "new", "value": NaN}',
        }[defect]
        file.write_text("\n".join(lines) + "\n")
        manifest["collections"]["users"].update(
            bytes=file.stat().st_size, sha256=hashlib.sha256(file.read_bytes()).hexdigest()
        )
    (path / "manifest.json").write_text(json.dumps(manifest))

    def forbidden_connection():
        pytest.fail("Invalid dataset opened a database connection")

    config = SimpleNamespace(
        settings={"dataset_directory": str(path), "replace_collections": True},
        get_database=forbidden_connection,
    )
    with pytest.raises(ValueError):
        load_dataset(config)


def test_validated_dataset_loads_all_records(tmp_path):
    from unittest.mock import Mock

    manifest = generate_dataset(tmp_path / "data", scale=0.01, seed=0, reference_date="2025-11-01")
    database = Mock()
    config = SimpleNamespace(
        settings={"dataset_directory": str(tmp_path / "data"), "replace_collections": True},
        get_database=lambda: database,
        get_create_indexes=lambda: True,
    )
    assert load_dataset(config) == manifest
    assert database.method_calls[0][0] == "ensure_ownership"
    assert database.method_calls[1][0] == "drop_collections"
    assert database.method_calls[2][0] == "create_collections"
    assert database.method_calls[-1][0] == "create_indexes"
    assert {
        call.args[0]: len(call.args[1]) for call in database.load_documents.call_args_list
    } == {name: metadata["count"] for name, metadata in manifest["collections"].items()}
