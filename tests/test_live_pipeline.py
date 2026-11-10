"""Small generated-data and short-run integration check; never a performance study."""

import copy
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from test_live_equivalence import assert_rows, normalize_mongo

from jsonbench.benchmark.benchmark import main as run_benchmark
from jsonbench.config_loader.config_loader import ConfigLoader
from jsonbench.data_generator.data_generator import generate_dataset, load_dataset
from jsonbench.query_generator.query_generator import generate_queries

pytestmark = pytest.mark.skipif(
    os.environ.get("JSONBENCH_LIVE") != "1", reason="opt-in live checks"
)
ROOT = Path(__file__).resolve().parents[1]


def test_generated_pipeline(tmp_path):
    from bondi.couchbase import CouchbaseExecutor, CouchbaseQuery
    from bondi.deployment import get_deployment
    from bondi.mongodb import MongoAggregateQuery, MongoCollectionRef, MongoExecutor
    from couchbase.n1ql import QueryScanConsistency

    output = Path(os.environ.get("JSONBENCH_SMOKE_OUTPUT", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    dataset = output / "dataset"
    manifest = generate_dataset(dataset, scale=0.05, seed=42, reference_date="2025-11-01")
    templates = json.loads((ROOT / "jsonbench/src/queries.json").read_text())
    # Keep the original literal test, then separately exercise a nonempty Q4 filter.
    tours = [json.loads(line) for line in (dataset / "tours.jsonl").read_text().splitlines()]
    location = tours[0]["itinerary"][0]["location"]
    nonempty = copy.deepcopy(templates[3])
    nonempty["name"] = "Query 4 (present location)"
    nonempty["operations"]["match"]["itinerary.location"] = location
    templates.append(nonempty)
    query_path = output / "queries.json"
    query_path.write_text(json.dumps(templates, indent=2))
    m = get_deployment("jsonbench-live-mongo")
    c = get_deployment("jsonbench-live-cb")
    namespace = "jsonbench_smoke_" + uuid4().hex[:12]
    configs = {}
    queries = {}
    created_scope = False
    report = {"collections": manifest["collections"], "queries": {}, "runs": {}}
    try:
        for backend, connection in [
            ("mongodb", {"uri": m.uri, "database": namespace}),
            (
                "couchbase",
                {
                    "uri": c.uri,
                    "username": c.username,
                    "password": c.password,
                    "bucket": c.bucket,
                    "scope": namespace,
                },
            ),
        ]:
            settings = {
                "database": backend,
                "connection": connection,
                "workers": 2,
                "duration": 3,
                "warmup_seconds": 1,
                "query_timeout_seconds": 10,
                "seed": 42,
                "scale_factor": 0.05,
                "create_indexes": True,
                "replace_collections": True,
                "dataset_directory": str(dataset),
                "results_directory": str(output / "runs"),
                "query_template_path": str(query_path),
                "query_selection_probability": [1 / len(templates)] * len(templates),
            }
            # Configuration file is ephemeral and may contain local test credentials.
            config_path = tmp_path / f"{backend}.json"
            config_path.write_text(json.dumps(settings))
            config = ConfigLoader(config_path)
            configs[backend] = config
            db = config.get_database()
            if backend == "couchbase":
                db.coll_mgr.create_scope(namespace)
                created_scope = True
            assert load_dataset(config) == manifest
            db.ensure_ownership()  # Existing valid marker permits future replacement.
            metadata = db.experiment_metadata()
            assert metadata["server_version"]
            assert metadata["indexes"]
            queries[backend] = generate_queries(config)

        with (
            MongoExecutor.from_uri(m.uri, timeout_seconds=30) as me,
            CouchbaseExecutor.from_uri(
                c.uri, username=c.username, password=c.password, timeout_seconds=30
            ) as ce,
        ):
            # Verify loaded content, not just the files supplied to the loader.
            for collection in manifest["collections"]:
                expected = [
                    json.loads(line)
                    for line in (dataset / f"{collection}.jsonl").read_text().splitlines()
                ]
                mr = me.run(
                    MongoAggregateQuery(MongoCollectionRef(namespace, collection), []),
                    collect_results=True,
                )
                cr = ce.run(
                    CouchbaseQuery(
                        f"SELECT RAW d FROM `{collection}` AS d",
                        query_context=f"{c.bucket}.{namespace}",
                    ),
                    collect_results=True,
                    query_kwargs={"scan_consistency": QueryScanConsistency.REQUEST_PLUS},
                )

                def canonical(rows):
                    return sorted(json.dumps(row, sort_keys=True) for row in rows)

                assert canonical(mr.documents) == canonical(expected) == canonical(cr.documents)
            for index, template in enumerate(templates):
                mr = me.run(
                    MongoAggregateQuery(
                        MongoCollectionRef(namespace, template["primary_collection"]),
                        queries["mongodb"][index]["query"],
                    ),
                    collect_results=True,
                )
                cr = ce.run(
                    CouchbaseQuery(
                        queries["couchbase"][index]["query"],
                        query_context=f"{c.bucket}.{namespace}",
                    ),
                    collect_results=True,
                    query_kwargs={"scan_consistency": QueryScanConsistency.REQUEST_PLUS},
                )
                assert_rows(normalize_mongo(mr.documents, template), cr.documents, template)
                report["queries"][template["name"]] = {
                    "rows": len(mr.documents),
                    "equivalent": True,
                }
            assert report["queries"][nonempty["name"]]["rows"] > 0

        for backend, config in configs.items():
            run = run_benchmark(config, queries[backend])
            info = json.loads((run / "info.json").read_text())
            events = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines()]
            summary = json.loads((run / "summary.json").read_text())
            started = {r["attempt_id"]: r for r in events if r["event"] == "started"}
            completed = [r for r in events if r["event"] == "completed"]
            assert info["state"] == "complete"
            assert set(started) == {r["attempt_id"] for r in completed}
            assert len(started) == len(completed)
            assert all(r["status"] == "success" for r in completed), completed
            assert all(
                0 <= r["start_seconds"] < 4 and r["finish_seconds"] >= r["start_seconds"]
                for r in completed
            )
            assert {r["name"] for r in completed} == {t["name"] for t in templates}
            for r in completed:
                assert r["row_count"] == report["queries"][r["name"]]["rows"]
            measured = [r for r in completed if 1 <= r["start_seconds"] < 4]
            in_window = [r for r in completed if 1 <= r["finish_seconds"] < 4]
            assert summary["successful_completion_throughput_qps"] == len(in_window) / 3
            assert summary["measurement_success_mean_seconds"] == pytest.approx(
                sum(r["time"] for r in measured) / len(measured)
            )
            assert summary["measurement_timeouts"] == summary["measurement_errors"] == 0
            report["runs"][backend] = {
                "run_id": run.name,
                "attempts": len(completed),
                "summary": summary,
            }
        (output / "report.json").write_text(json.dumps(report, indent=2))
    finally:
        if "mongodb" in configs and configs["mongodb"].database is not None:
            configs["mongodb"].database.client.drop_database(namespace)
        if created_scope:
            configs["couchbase"].database.coll_mgr.drop_scope(namespace)
        for config in configs.values():
            config.close()
