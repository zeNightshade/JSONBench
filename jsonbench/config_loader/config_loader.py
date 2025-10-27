import jsonbench.database_connectors.mongodb as mdb
import jsonbench.database_connectors.couchbase as cb

import json
import sys

CONFIG_PATH = "jsonbench/src/config.json"

def load_data_generation_config(path=CONFIG_PATH):
    with open(path) as f:
        config = json.load(f)

        database = config["database"]
        scale_factor = float(config["scale_factor"])

        # Load corresponding database connector
        if database == "mongodb":
            database = mdb.MongoDB()
        elif database == "couchbase":
            database = cb.Couchbase()
        else:
            print("Invalid database in configuration file!")
            sys.exit(1)
        
    return (database, scale_factor)

def load_benchmark_config(path=CONFIG_PATH):
    with open(path) as f:
        config = json.load(f)

        database = config["database"]
        workers = config["workers"]
        duration = config["duration"]

        # Load corresponding database connector
        if database == "mongodb":
            database = mdb.MongoDB()
        elif database == "couchbase":
            database = cb.Couchbase()
        else:
            print("Invalid database in configuration file!")
            sys.exit(1)
        
    return (database, workers, duration)
