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
