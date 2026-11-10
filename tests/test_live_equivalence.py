"""Opt-in native execution against BONDI-managed, isolated local databases.

Deployment creation is explicit; this module only owns its unique database/scope.
"""

import json
import os
import time
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from jsonbench.query_generator.cb_query_gen import CouchbaseQueryGenerator
from jsonbench.query_generator.mdb_query_gen import MongoDBQueryGenerator

pytestmark = pytest.mark.skipif(
    os.environ.get("JSONBENCH_LIVE") != "1", reason="opt-in live checks"
)
ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = json.loads((ROOT / "jsonbench/src/queries.json").read_text())
FIXTURE = json.loads((ROOT / "tests/fixtures/travel-equivalence.json").read_text())


@pytest.fixture(scope="module")
def live_databases():
    from bondi.couchbase import CouchbaseExecutor
    from bondi.deployment import get_deployment
    from bondi.mongodb import MongoExecutor
    from couchbase.auth import PasswordAuthenticator
    from couchbase.cluster import Cluster
    from couchbase.exceptions import (
        BucketNotFoundException,
        CollectionNotFoundException,
        ScopeNotFoundException,
    )
    from couchbase.options import ClusterOptions
    from pymongo import MongoClient

    mongo = get_deployment(os.environ.get("JSONBENCH_MONGO_DEPLOYMENT", "jsonbench-live-mongo"))
    couch = get_deployment(os.environ.get("JSONBENCH_CB_DEPLOYMENT", "jsonbench-live-cb"))
    namespace = "jsonbench_check_" + uuid4().hex[:12]
    client = MongoClient(mongo.uri)
    cluster = Cluster(
        couch.uri, ClusterOptions(PasswordAuthenticator(couch.username, couch.password))
    )
    cluster.wait_until_ready(timedelta(seconds=20))
    manager = cluster.bucket(couch.bucket).collections()
    scope_created = False
    try:
        manager.create_scope(namespace)
        scope_created = True
        scope = cluster.bucket(couch.bucket).scope(namespace)
        for name, documents in FIXTURE["documents"].items():
            client[namespace].create_collection(name)
            if documents:
                client[namespace][name].insert_many(documents)
            manager.create_collection(namespace, name)
            destination = scope.collection(name)
            for document in documents:
                destination.upsert(document["_id"], document)
            # Correctness fixtures need scan access, not performance-tuned indexes.
            indexes = destination.query_indexes()
            deadline = time.monotonic() + 30
            while True:
                try:
                    indexes.create_primary_index(timeout=timedelta(seconds=10))
                    break
                except (
                    BucketNotFoundException,
                    ScopeNotFoundException,
                    CollectionNotFoundException,
                ):
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.2)
            indexes.watch_indexes(["#primary"], timeout=timedelta(seconds=60))
        with (
            MongoExecutor.from_uri(mongo.uri, timeout_seconds=30) as me,
            CouchbaseExecutor.from_uri(
                couch.uri, username=couch.username, password=couch.password, timeout_seconds=30
            ) as ce,
        ):
            yield namespace, couch.bucket, me, ce, client, scope
    finally:
        client.drop_database(namespace)
        client.close()
        if scope_created:
            manager.drop_scope(namespace)
        cluster.close()


def normalize_mongo(rows, template):
    by = template["operations"]["group"]["by"]
    result = []
    for original in rows:
        row = dict(original)
        key = row.pop("_id")
        if isinstance(by, list) or "." in by:
            row.update(key)
        else:
            row[by] = key
        result.append(row)
    return result


def assert_rows(actual, expected, template):
    by = template["operations"]["group"]["by"]
    names = [x.replace(".", "_") for x in (by if isinstance(by, list) else [by])]

    def key(row):
        return tuple(row[name] for name in names)

    assert len(actual) == len(expected)
    for actual_row, expected_row in zip(
        sorted(actual, key=key), sorted(expected, key=key), strict=True
    ):
        assert actual_row.keys() == expected_row.keys()
        for field, value in expected_row.items():
            assert actual_row[field] == (
                pytest.approx(value) if isinstance(value, (int, float)) else value
            )


@pytest.mark.parametrize("template", TEMPLATES, ids=[t["name"] for t in TEMPLATES])
def test_native_query_equivalence(live_databases, template):
    from bondi.couchbase import CouchbaseQuery
    from bondi.mongodb import MongoAggregateQuery, MongoCollectionRef
    from couchbase.n1ql import QueryScanConsistency

    namespace, bucket, mongo, couch, _, _ = live_databases
    pipeline = MongoDBQueryGenerator().generate_query(template)
    sql = CouchbaseQueryGenerator().generate_query(template)
    mongo_result = mongo.run(
        MongoAggregateQuery(
            MongoCollectionRef(namespace, template["primary_collection"]), pipeline
        ),
        collect_results=True,
    )
    couch_result = couch.run(
        CouchbaseQuery(sql, query_context=f"{bucket}.{namespace}"),
        collect_results=True,
        query_kwargs={"scan_consistency": QueryScanConsistency.REQUEST_PLUS},
    )
    expected = FIXTURE["expected"][template["name"]]
    assert_rows(normalize_mongo(mongo_result.documents, template), expected, template)
    assert_rows(couch_result.documents, expected, template)


@pytest.mark.parametrize("mode", ["quoted_filter", "projection_sort_limit"])
def test_native_scalar_operations(live_databases, mode):
    from bondi.couchbase import CouchbaseQuery
    from bondi.mongodb import MongoAggregateQuery, MongoCollectionRef
    from couchbase.n1ql import QueryScanConsistency

    namespace, bucket, mongo, couch, _, _ = live_databases
    operations = {"project": {"name": 1}, "sort": {"field": "name", "direction": 1}, "limit": 2}
    expected = [{"name": "Alpha"}, {"name": "Beta"}]
    if mode == "quoted_filter":
        name = FIXTURE["documents"]["tours"][0]["name"]
        operations["match"] = {"name": name}
        expected = [{"name": name}]
    template = {"primary_collection": "tours", "operations": operations}
    m = mongo.run(
        MongoAggregateQuery(
            MongoCollectionRef(namespace, "tours"), MongoDBQueryGenerator().generate_query(template)
        ),
        collect_results=True,
    )
    c = couch.run(
        CouchbaseQuery(
            CouchbaseQueryGenerator().generate_query(template),
            query_context=f"{bucket}.{namespace}",
        ),
        collect_results=True,
        query_kwargs={"scan_consistency": QueryScanConsistency.REQUEST_PLUS},
    )
    assert [{k: v for k, v in row.items() if k != "_id"} for row in m.documents] == expected
    assert c.documents == expected


@pytest.mark.parametrize("template", TEMPLATES, ids=[t["name"] for t in TEMPLATES])
def test_jsonbench_connectors_consume_live_queries(live_databases, template):
    from jsonbench.database_connectors.couchbase import Couchbase
    from jsonbench.database_connectors.mongodb import MongoDB

    namespace, _, _, _, client, scope = live_databases
    mongo = MongoDB.__new__(MongoDB)
    mongo.database = client[namespace]
    couch = Couchbase.__new__(Couchbase)
    couch.cb_scope = scope
    for connector, compiler in [
        (mongo, MongoDBQueryGenerator()),
        (couch, CouchbaseQueryGenerator()),
    ]:
        outcome = connector.query(
            template["primary_collection"], compiler.generate_query(template), timeout_seconds=30
        )
        assert outcome["status"] == "success", outcome
        assert outcome["row_count"] == len(FIXTURE["expected"][template["name"]])
        assert outcome["time"] >= 0
