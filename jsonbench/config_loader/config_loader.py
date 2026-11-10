"""Validated configuration; loading configuration never opens a connection."""

import json
import math


class ConfigLoader:
    def __init__(self, path="jsonbench/src/config.json"):
        with open(path) as file:
            self.settings = json.load(file)
        self.database_type = self.settings["database"]
        if self.database_type not in {"mongodb", "couchbase"}:
            raise ValueError("Unknown database")
        for key, default, allow_zero in [
            ("duration", 180, False),
            ("warmup_seconds", 60, True),
            ("query_timeout_seconds", 60, False),
        ]:
            value = self.settings.setdefault(key, default)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"{key} must be finite")
            if value < 0 or (value == 0 and not allow_zero):
                raise ValueError(f"Invalid {key}")
        workers = self.settings["workers"]
        if type(workers) is not int or workers <= 0:
            raise ValueError("workers must be a positive integer")
        seed = self.settings.setdefault("seed", 0)
        if type(seed) is not int:
            raise ValueError("seed must be an integer")
        self.database = None

    def get_database(self):
        if self.database is None:
            connection = self.settings.get("connection", {})
            if self.database_type == "mongodb":
                from jsonbench.database_connectors.mongodb import MongoDB

                self.database = MongoDB(**connection)
            else:
                from jsonbench.database_connectors.couchbase import Couchbase

                self.database = Couchbase(**connection)
        return self.database

    def close(self):
        if self.database is not None:
            self.database.close()
            self.database = None

    def get_query_gen(self):
        if self.database_type == "mongodb":
            from jsonbench.query_generator.mdb_query_gen import MongoDBQueryGenerator

            return MongoDBQueryGenerator()
        from jsonbench.query_generator.cb_query_gen import CouchbaseQueryGenerator

        return CouchbaseQueryGenerator()

    def get_database_type(self):
        return self.database_type

    def get_create_indexes(self):
        return self.settings["create_indexes"]

    def get_scale_factor(self):
        return float(self.settings["scale_factor"])

    def get_workers(self):
        return self.settings["workers"]

    def get_duration(self):
        return self.settings["duration"]

    def get_query_template_path(self):
        return self.settings["query_template_path"]

    def get_query_sel_prob(self):
        return self.settings["query_selection_probability"]

    def display_config(self, generate_data=False):
        print(
            f"Database: {self.database_type}; workers: {self.get_workers()}; "
            f"measurement seconds: {self.get_duration()}"
        )
