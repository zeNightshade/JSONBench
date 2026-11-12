import copy
import json
from pathlib import Path

import pytest

from jsonbench.query_generator.cb_query_gen import CouchbaseQueryGenerator
from jsonbench.query_generator.mdb_query_gen import MongoDBQueryGenerator

GENERATORS = [MongoDBQueryGenerator, CouchbaseQueryGenerator]
QUERIES = json.loads(
    (Path(__file__).resolve().parents[1] / "jsonbench/src/queries.json").read_text()
)


@pytest.mark.parametrize("generator", GENERATORS)
@pytest.mark.parametrize("template", QUERIES)
def test_all_templates_compile_without_mutation(generator, template):
    before = copy.deepcopy(template)
    first = generator().generate_query(template)
    assert first == generator().generate_query(template)
    assert template == before


def test_q8_unnest_reference_is_exact():
    query = CouchbaseQueryGenerator().generate_query(QUERIES[7])
    assert "UNNEST `bookings`.`travellers` AS `__unnest_0`" in query
    assert "`__unnest_0`.`nationality`" in query
    assert "AVG(`reviews`.`rating`)" in query


def test_nested_size_expression():
    assert MongoDBQueryGenerator().parse_expr("avg(size(travellers))") == {
        "$avg": {"$size": "$travellers"}
    }
    assert "AVG(ARRAY_LENGTH(`bookings`.`travellers`))" in CouchbaseQueryGenerator().generate_query(
        QUERIES[2]
    )


def test_projection_and_sort():
    template = {
        "primary_collection": "tours",
        "operations": {"project": {"name": 1}, "sort": {"field": "name", "direction": -1}},
    }
    assert MongoDBQueryGenerator().generate_query(template) == [
        {"$project": {"name": 1}},
        {"$sort": {"name": -1}},
    ]
    assert "ORDER BY `name` DESC" in CouchbaseQueryGenerator().generate_query(template)


def test_literal_quotes_are_escaped():
    value = 'O\'Brien "quoted" \\ path'
    template = {"primary_collection": "tours", "operations": {"match": {"name": value}}}
    assert json.dumps(value) in CouchbaseQueryGenerator().generate_query(template)


@pytest.mark.parametrize("generator", GENERATORS)
@pytest.mark.parametrize(
    "operations",
    [
        {"unknown": {}},
        {"match": {"x": None}},
        {"match": {"x": {"$gt": 2}}},
        {"group": {"by": "x", "aggregates": {"y": "avg(sum(x))"}}},
        {"limit": -1},
        {"sort": {"field": "x", "direction": "DESC"}},
    ],
)
def test_unsupported_syntax_rejected(generator, operations):
    with pytest.raises(ValueError):
        generator().generate_query({"primary_collection": "tours", "operations": operations})
