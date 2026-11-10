# Benchmarking JSON Document Stores for Analytical Workloads

Developed in partial fulfillment of the requirements for the degree of Bachelor of Advanced Computing (Honours) at The University of Sydney.

---

## Overview

JSONBench is a Python-based benchmark designed to evaluate the analytical performance of JSON document stores. Existing benchmarks such as TPC-H and YCSB primarily target relational databases or simple key-value workloads, providing limited support for the unique characteristics of JSON document stores.

This project addresses these limitations by providing a configurable benchmark capable of evaluating databases using realistic analytical workloads involving:

- Nested JSON documents
- Arrays and unnesting operations
- Multi-collection joins
- Aggregation queries
- Concurrent analytical workloads
- Configurable dataset sizes and workload distributions

The benchmark currently supports MongoDB and Couchbase through language-specific query generators while maintaining database-independent query templates.

---

## Features

- Extensible benchmark architecture
- Configurable data generation
- Realistic JSON document schemas
- Analytical workload simulation
- Database-independent query templates
- Automatic query generation for multiple query languages
- Concurrent workload execution
- Throughput and latency measurement
- Reproducible benchmarking experiments
- Modular design for adding additional types of JSON document stores

---

## Benchmark Architecture

The benchmark consists of several independent modules:

- **Configuration Loader**
  - Loads benchmark parameters from the configuration file

- **Data Generator**
  - Generates realistic synthetic datasets

- **Query Generator**
  - Converts abstract query templates into database-specific query languages

- **Benchmark Driver**
  - Executes workloads using configurable concurrency

- **Database Driver**
  - Handles communication with supported databases

- **Results Logger**
  - Records benchmark execution metrics

---

## Schema

The benchmark models a realistic **tour booking platform** consisting of four collections:

- Users
- Tours
- Bookings
- Reviews

The schema intentionally incorporates embedded documents, references, nested arrays, and variable-length structures to better represent modern production applications.

---

## Workloads

The benchmark includes representative analytical queries covering:

- Revenue analysis
- Traveller demographics
- Group size analysis
- Destination popularity
- Review aggregation
- Age distributions
- Multi-collection joins
- Nested array processing

These workloads exercise various operations such as aggregation, filtering, grouping, joins, and array unnesting.

---

## Configuration

Benchmark execution is controlled using a JSON configuration file.

Example:

```json
{
  "database": "mongodb",
  "create_indexes": true,
  "scale_factor": 100,
  "workers": 32,
  "duration": 500,
  "query_template_path": "queries.json"
}
```

Key configurable parameters include:

- Database
- Scale factor
- Number of concurrent workers
- Benchmark duration
- Query selection probabilities
- Secondary index creation

---

## Running the Benchmark

### Install dependencies

```bash
pip install -r requirements.txt
```

### Generate canonical benchmark data (offline)

```bash
python -m jsonbench -d
```

Generation creates a new dataset directory and refuses to overwrite one. Configure
`dataset_directory`, `seed`, `reference_date`, and `scale_factor` in
`jsonbench/src/config.json`. This generator version changes the old random sequence;
its artifacts are a new benchmark dataset, not a reconstruction of historical data.

### Load the same artifact into a selected database

Set `database` and optional `connection` in the configuration. MongoDB connection
keys are `uri` and `database`; Couchbase keys are `uri`, `username`, `password`,
`bucket`, and `scope`. Loading replaces the four benchmark collections and therefore
requires `replace_collections: true` explicitly. Use a dedicated benchmark database
or scope. Generate once, then load that artifact separately into each backend.
Before connecting, the loader validates the manifest version, all four collections,
checksums, byte sizes, record counts, valid JSON and unique nonempty string IDs
(up to 250 UTF-8 bytes). Keep dataset files unchanged during loading. This preflight
does not verify destination ownership or make database replacement transactional.

```sh
python -m jsonbench --load
```

### Execute benchmark

```bash
python -m jsonbench
```

---

## Performance Metrics

JSONBench measures:

- Throughput
- Query latency
- Scalability
- Query execution time
- Concurrent workload performance

Results are written to the configured output directory for further analysis.

---

## Evaluation

The historical MongoDB/Couchbase evaluation is under correctness review. Its
published latency, throughput, and pooled per-query plots must not be used as
validated comparisons. See the revised `visualisation.ipynb` for diagnostic
analysis and [TODO.md](TODO.md) for remaining work before rerunning experiments.

---

## Technologies

- Python
- MongoDB
- Couchbase
- MongoDB Query Language (MQL)
- SQL++
- Faker
- pandas
- Matplotlib

---

## Correctness work and legacy result analysis

See [TODO.md](TODO.md) for the prioritised repair plan. The original latency and
throughput plots are not reliable performance comparisons. The revised
`visualisation.ipynb` reports numeric query durations and missing-timing rates;
it intentionally does not estimate throughput from these legacy logs.

Place the supplied logs under `jsonbench/results/`, then launch the notebook from
the repository root. `legacy-runs.json` records the historical run selection.
The logs do not contain measurement boundaries, error details, or query results,
so reanalysis cannot establish exact throughput or query equivalence.

Run the offline analysis tests with:

```sh
uv run --with-requirements requirements-dev.txt python -m pytest tests
uv run --with ruff ruff check jsonbench tests
```

Python 3.11+ is required. No database is needed for the unit tests or legacy analysis.
See [measurement protocol](docs/measurement-protocol.md) and
[template semantics](docs/query-templates.md) for the repaired runner and compiler.
Live correctness validation and the remaining TODO items are still required before
publication reruns. The eight core queries and both query connectors pass the opt-in
[BONDI live fixture checks](docs/live-validation.md) on MongoDB 8.0.16 and Couchbase
Community 7.6.2. Generated-data equivalence and the paper versions remain pending.
