"""Read-only, disk-backed comparison of loaded content with a canonical artifact."""

import hashlib
import json
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from .data_generator import validate_dataset


def _canonical(value):
    # JSON numbers have no integer/float type distinction across these databases.
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    return value


def _digest(document):
    return hashlib.sha256(json.dumps(
        _canonical(document), sort_keys=True, allow_nan=False, separators=(",", ":")
    ).encode()).hexdigest()


def verify_dataset(database, directory, templates):
    path = Path(directory)
    manifest = validate_dataset(path)
    q4 = next((q for q in templates if q["name"] == "Query 4"), None)
    location = q4["operations"]["match"]["itinerary.location"] if q4 else None
    selectivity = {"location": location, "total_tours": 0, "matching_tours": 0,
                   "total_itinerary_visits": 0, "matching_itinerary_visits": 0}
    counts = {}
    with tempfile.TemporaryDirectory(prefix="jsonbench-verify-") as temporary:
        with sqlite3.connect(Path(temporary) / "documents.sqlite") as index:
            index.execute("CREATE TABLE expected (id TEXT PRIMARY KEY, digest TEXT, seen INTEGER)")
            for collection in manifest["collections"]:
                index.execute("DELETE FROM expected")
                with (path / f"{collection}.jsonl").open() as file:
                    for line in file:
                        document = json.loads(line)
                        index.execute("INSERT INTO expected VALUES (?, ?, 0)",
                                      (document["_id"], _digest(document)))
                count = 0
                rows = database.iter_documents(collection)
                try:
                    for document in rows:
                        identity = document.get("_id")
                        row = index.execute("SELECT digest, seen FROM expected WHERE id = ?",
                                            (identity,)).fetchone()
                        if row is None or row[1] or row[0] != _digest(document):
                            raise ValueError(f"Loaded dataset mismatch in {collection}: {identity!r}")
                        index.execute("UPDATE expected SET seen = 1 WHERE id = ?", (identity,))
                        count += 1
                        if collection == "tours" and q4:
                            visits = document["itinerary"]
                            matches = sum(v["location"] == location for v in visits)
                            selectivity["total_tours"] += 1
                            selectivity["matching_tours"] += bool(matches)
                            selectivity["total_itinerary_visits"] += len(visits)
                            selectivity["matching_itinerary_visits"] += matches
                finally:
                    close = getattr(rows, "close", None)
                    if close:
                        close()
                if count != manifest["collections"][collection]["count"]:
                    raise ValueError(f"Loaded dataset missing documents in {collection}")
                counts[collection] = count
    if q4:
        total = selectivity["total_itinerary_visits"]
        selectivity["visit_selectivity"] = (
            selectivity["matching_itinerary_visits"] / total if total else None
        )
        selectivity["zero_matches"] = selectivity["matching_itinerary_visits"] == 0
    return {
        "verified_at": datetime.now(UTC).isoformat(),
        "manifest_sha256": hashlib.sha256((path / "manifest.json").read_bytes()).hexdigest(),
        "collections": counts,
        "q4_selectivity": selectivity if q4 else None,
    }


def verify_config(config):
    templates = json.loads(Path(config.get_query_template_path()).read_text())
    return verify_dataset(config.get_database(), config.settings["dataset_directory"], templates)
