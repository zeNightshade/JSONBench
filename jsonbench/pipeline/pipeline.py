from jsonbench.benchmark import benchmark
from jsonbench.config_loader import config_loader
from jsonbench.data_generator import data_generator
from jsonbench.query_generator import query_generator

def main(args):
    print("=" * 101)
    print(f"{' ' * 40}Welcome to JSONBench!")
    print("=" * 101)
    
    config = config_loader.ConfigLoader()

    if len(args) != 0 and args[0] == "-d":
        # Data generation mode
        data_generator.main(config)
    else:
        # Query generation and benchmarking mode
        queries = query_generator.main(config)
        benchmark.main(config, queries)