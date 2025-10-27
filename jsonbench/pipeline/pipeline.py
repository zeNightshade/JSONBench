from jsonbench.config_loader import config_loader
from jsonbench.data_generator import data_generator


def main(args):
    print("=" * 101)
    print(f"{' ' * 40}Welcome to JSONBench!")
    print("=" * 101)
    
    
    if len(args) != 0 and args[0] == "-d":
        # Data generation mode
        database, scale_factor = config_loader.load_data_generation_config()
        data_generator.main(database, scale_factor)
    else:
        # Benchmarking mode
        database, workers, duration = config_loader.load_benchmark_config()
        # run_benchmark()