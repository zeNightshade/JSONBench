from alive_progress import alive_bar
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import numpy as np

import json
import os
import time


def setup_results_dir(config):
    name = input("Provide a name for this benchmarking run: ")
    db_type = config.get_database_type()
    date = datetime.today().strftime("%Y%m%d-%H%M")

    os.makedirs(f"jsonbench/results/{db_type}/{date}", exist_ok=True)

    run_info = {
        "name": name,
        "workers": config.get_workers(),
        "duration": config.get_duration(),
        "query_selection_probability": config.get_query_sel_prob()
    }

    with open(f"jsonbench/results/{db_type}/{date}/info.json", 'w+') as f:
        json.dump(run_info, f, indent=4)

def benchmark(config, queries):
    database = config.get_database()
    db_type = config.get_database_type()
    query_sel_prob = config.get_query_sel_prob()
    date = datetime.today().strftime("%Y%m%d-%H%M")
    target_end_time = time.time() + config.get_duration()
    results = []
    
    while time.time() < target_end_time:
        query = np.random.choice(queries, p=query_sel_prob)
        start_time = time.perf_counter()
        database.query(query["primary_collection"], query["query"])
        end_time = time.perf_counter()
        elapsed_time = end_time - start_time
        results.append({
            "name": query["name"],
            "time": elapsed_time
        })

    with open(f"jsonbench/results/{db_type}/{date}/results.json", 'w+') as f:
        json.dump(results, f, indent=4)

    print(f"========== Queries executed: {len(results)} ==========")

def main(config, queries):
    setup_results_dir(config)
    
    print("> Starting benchmarking process...")
    print("-"*50)
    print("> Benchmarking database with queries...")

    workers = config.get_workers()

    with alive_bar(unknown="stars", spinner=None, monitor=False, elapsed="{elapsed}", stats=False) as bar:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for _ in range(workers):
                executor.submit(benchmark, config, queries)

    print("> Benchmarking completed successfully!")
    print("> Results of queries are saved in the results folder")