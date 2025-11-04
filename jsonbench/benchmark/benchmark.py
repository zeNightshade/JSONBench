from alive_progress import alive_bar
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import numpy as np

import json
import os
import time


def store_results(config, results):
    db_type = config.get_database_type()
    date = datetime.today().strftime("%Y%m%d-%H%M")

    os.makedirs(f"jsonbench/results/{db_type}/{date}", exist_ok=True)

    run_info = {
        "workers": config.get_workers(),
        "duration": config.get_duration(),
        "query_selection_probability": config.get_query_sel_prob()
    }

    with open(f"jsonbench/results/{db_type}/{date}/info.json", 'w+') as f:
        json.dump(run_info, f, indent=4)

    with open(f"jsonbench/results/{db_type}/{date}/results.json", 'w+') as f:
        json.dump(results, f, indent=4)

    print(f"> Results of queries are saved in: jsonbench/results/{db_type}/{date}")

def benchmark(config, queries):
    database = config.get_database()
    query_sel_prob = config.get_query_sel_prob()
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
    
    # print(f"========== Queries executed: {len(results)} ==========")
    
    return results

def main(config, queries): 
    print("> Starting benchmarking process...")
    print("-"*50)
    print("> Benchmarking database with queries...")

    workers = config.get_workers()

    with alive_bar(unknown="stars", spinner=None, monitor=False, elapsed="{elapsed}", stats=False) as bar:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_benchmark = {executor.submit(benchmark, config, queries): _ for _ in range(workers)}
    
    results = []

    for future in as_completed(future_benchmark):
        results.append(future.result())

    store_results(config, results)

    print("> Benchmarking completed successfully!")