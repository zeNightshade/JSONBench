from jsonbench.data_generator import data_generator
from jsonbench.query_generator import query_generator
from jsonbench.config_loader import config_loader


def main(args):
    print("=" * 101)
    print(f"{' ' * 40}Welcome to JSONBench!")
    print("=" * 101)
    
    if len(args) != 0:
        config = config_loader.ConfigLoader(args[0])
    else:
        config = config_loader.ConfigLoader()

    if config.get_generate_data():
        # Data generation mode
        data_generator.main(config)
    else:
        # Benchmarking mode
        query_generator.main(config)