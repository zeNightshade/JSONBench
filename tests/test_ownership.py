from unittest.mock import Mock

import pytest

from jsonbench.database_connectors.ownership import MARKER, validate_ownership


@pytest.mark.parametrize("names,marker", [
    ({"users"}, None),
    ({"unrelated"}, None),
    ({"jsonbench_metadata"}, None),
    ({"users"}, {"owner": "someone else"}),
    ({"users"}, {**MARKER, "collections": ["users"]}),
])
def test_unowned_or_invalid_destination_refused(names, marker):
    with pytest.raises(ValueError):
        validate_ownership(names, marker)


def test_empty_destination_and_valid_marker():
    validate_ownership(set(), None)
    validate_ownership({"users", "jsonbench_metadata"}, MARKER)


def test_loader_does_not_drop_when_ownership_fails(tmp_path):
    from types import SimpleNamespace

    from jsonbench.data_generator.data_generator import generate_dataset, load_dataset

    generate_dataset(tmp_path / "data", scale=0.01, seed=1, reference_date="2025-11-01")
    database = Mock()
    database.ensure_ownership.side_effect = ValueError("unowned")
    config = SimpleNamespace(
        settings={"dataset_directory": str(tmp_path / "data"), "replace_collections": True},
        get_database=lambda: database,
    )
    with pytest.raises(ValueError, match="unowned"):
        load_dataset(config)
    database.drop_collections.assert_not_called()
    database.create_collections.assert_not_called()
    database.load_documents.assert_not_called()
