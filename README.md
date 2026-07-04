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
  - Loads benchmark parameters from the configuration file.

- **Data Generator**
  - Generates realistic synthetic datasets.

- **Query Generator**
  - Converts abstract query templates into database-specific query languages.

- **Benchmark Driver**
  - Executes workloads using configurable concurrency.

- **Database Driver**
  - Handles communication with supported databases.

- **Results Logger**
  - Records benchmark execution metrics.

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

### Generate benchmark data

```bash
python jsonbench -d
```

### Execute benchmark

```bash
python jsonbench
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

## Technologies

- Python
- MongoDB
- Couchbase
- MongoDB Query Language (MQL)
- SQL++
- Faker
- pandas
- NumPy
- Matplotlib

---
