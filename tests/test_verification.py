import json
from types import SimpleNamespace

import pytest

from jsonbench.data_generator.data_generator import generate_dataset
from jsonbench.data_generator.verification import verify_dataset


@pytest.mark.parametrize("defect", [None, "changed", "missing", "extra", "duplicate"])
def test_full_content_verification(tmp_path, defect):
    manifest = generate_dataset(tmp_path / "data", scale=0.01, seed=1,
                                reference_date="2025-11-01")
    data = {name: [json.loads(line) for line in
                  (tmp_path / "data" / f"{name}.jsonl").read_text().splitlines()]
            for name in manifest["collections"]}
    location = data["tours"][0]["itinerary"][0]["location"]
    templates = [{"name": "Query 4", "operations": {"match": {"itinerary.location": location}}}]
    if defect == "changed":
        data["users"][0]["name"] = "changed"
    elif defect == "missing":
        data["users"].pop()
    elif defect == "extra":
        data["users"].append({"_id": "extra"})
    elif defect == "duplicate":
        data["users"].append(data["users"][0])
    database = SimpleNamespace(iter_documents=lambda name: iter(reversed(data[name])))
    if defect:
        with pytest.raises(ValueError, match="Loaded dataset"):
            verify_dataset(database, tmp_path / "data", templates)
    else:
        result = verify_dataset(database, tmp_path / "data", templates)
        assert result["collections"] == {k: v["count"] for k, v in manifest["collections"].items()}
        q4 = result["q4_selectivity"]
        assert q4["matching_itinerary_visits"] == sum(
            v["location"] == location for t in data["tours"] for v in t["itinerary"]
        )
        assert q4["matching_tours"] >= 1
        templates[0]["operations"]["match"]["itinerary.location"] = "absent-location"
        assert verify_dataset(database, tmp_path / "data", templates)["q4_selectivity"]["zero_matches"]
