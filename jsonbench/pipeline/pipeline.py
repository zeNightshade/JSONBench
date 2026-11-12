import json

from jsonbench.benchmark.supervisor import run_supervised
from jsonbench.config_loader import config_loader
from jsonbench.data_generator import data_generator
from jsonbench.data_generator.verification import verify_config
from jsonbench.query_generator import query_generator


def main(args):
    print("=" * 101)
    print(f"{' ' * 40}Welcome to JSONBench!")
    print("=" * 101)

    config = config_loader.ConfigLoader()

    try:
        if len(args) != 0 and args[0] == "-d":
            # Data generation mode
            data_generator.main(config)
        elif args and args[0] == "--verify":
            print(json.dumps(verify_config(config), indent=2))
        elif args and args[0] == "--load":
            data_generator.load_dataset(config)
        else:
            # Query generation and benchmarking mode
            queries = query_generator.main(config)
            run_supervised(config, queries)
    finally:
        config.close()
