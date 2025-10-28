from alive_progress import alive_it

import numpy as np

import json
import time


def generate_queries(config):
    print("> Generating queries from templates...")

    with open(config.get_query_template_path()) as f:
        templates = json.load(f)
    
    queries = []

    for template in alive_it(templates):
        query = config.get_query_gen().generate_query(template)
        queries.append({
            "name": template["name"],
            "description": template["description"],
            "primary_collection": template["primary_collection"],
            "query": query
        })

    print("> Queries generated successfully!")

    return queries

def benchmark(config, queries):
    print("> Benchmarking database with queries...")

    database = config.get_database()
    db_type = config.get_database_type()
    query_sel_prob = config.get_query_sel_prob()
    results = []

    overall_start_time = time.perf_counter()

    for _ in alive_it(range(config.get_duration())):
        # Warm-up code here

        query = np.random.choice(queries, p=query_sel_prob)
        start_time = time.perf_counter()
        database.query(query["primary_collection"], query["query"])
        end_time = time.perf_counter()
        elapsed_time = end_time - start_time
        results.append({
            "name": query["name"],
            "time": elapsed_time
        })

        # Cool-down code here

    overall_end_time = time.perf_counter()
    overall_elapsed_time = overall_end_time - overall_start_time
    print(f"========== Execution time: {overall_elapsed_time:.6f} seconds ==========")

    with open(f"jsonbench/results/{db_type}/benchmark.json", 'w+') as f:
        json.dump(results, f, indent=4)

    # for query in alive_it(queries):
    #     results = database.query(query["primary_collection"], query["query"])
        
    #     with open(f"jsonbench/results/{db_type}/{query["name"]}.json", 'w+') as f:
    #         json.dump(list(results), f, indent=4)

    print("> Benchmarking completed successfully!")

def main(config):
    print("> Starting query generation and benchmarking process...")
    print("-" * 50)

    queries = generate_queries(config)
    benchmark(config, queries)

    print("> Query generation and benchmarking completed successfully!")
    print("> Results of queries are saved in the results folder")