# Live query-equivalence checks with BONDI

These are small correctness tests, not performance experiments. BONDI manages the
containers and executes the generated native queries with `collect_results=True`.
JSONBench's own connectors are also exercised for full consumption and row counts.
BONDI is a test-time tool here; the benchmark has no runtime dependency on a sibling
checkout.

## Start isolated deployments

With Docker running and these ports free, use the local BONDI checkout:

```sh
uv run --project ~/code/bondi bondi deploy mongodb --name jsonbench-live-mongo \
  --port 27029 --version 8.0.16 --memory-limit-mb 1024 --wiredtiger-cache-size-gb 0.25
uv run --project ~/code/bondi bondi deploy couchbase --name jsonbench-live-cb \
  --management-port 9591 --query-port 9593 --kv-port 11219 \
  --version 7.6.2 --edition community --bucket jsonbench_live
```

The test suite expects existing running deployments. Override their names with
`JSONBENCH_MONGO_DEPLOYMENT` and `JSONBENCH_CB_DEPLOYMENT`. It creates a unique
MongoDB database and Couchbase scope for each run, and removes only those test-owned
namespaces afterward. Deployment data/configuration is not removed.

From the JSONBench repository root:

```sh
JSONBENCH_LIVE=1 uv run --with ~/code/bondi --with-requirements requirements-dev.txt \
  python -m pytest tests/test_live_equivalence.py -q
```

Normal unit tests skip live checks. A published compatible BONDI installation may
also be used instead of `--with ~/code/bondi`.

## What is checked

`tests/fixtures/travel-equivalence.json` contains ten documents and explicit expected
answers, calculated independently from the compiler. Coverage includes:

- Empty traveller/itinerary arrays and a tour without matching bookings/reviews.
- Booking sizes 1 and 3 (mean 2, not traveller-weighted 2.5).
- Multiple reviews and traveller nationalities, exposing Q8 multiplicities.
- Repeated visits to the same destination, exposing Q4 and Q7 multiplicities.
- Quoted/backslash-containing strings, inclusion projection, sort, and limit.
- Fully consumed numeric outcomes from JSONBench's own connectors for all eight queries.

MongoDB grouping keys are normalised into the SQL++ field layout. Row order is
ignored for unsorted aggregation queries, numeric values use tolerance, and row
multiplicity is retained. Ordered projection tests compare the complete sequence.
Couchbase uses request-plus consistency for expected-answer checks and primary indexes
for scan access. These indexes are a correctness-fixture setup, not a benchmark
index recommendation. Creation waits for Query-service visibility and index readiness.

The fixture pins existing Q4/Q8 semantics, not an endorsement of their intended
business meaning. Q4 counts itinerary visits; Q8 joins all reviews to all travellers
within a tour. Those research decisions remain open.

## Observed validation

Validated locally with BONDI 0.1.9, MongoDB 8.0.16, Couchbase Community 7.6.2.
These differ from the paper's MongoDB 8.2.1 and Couchbase 8.0.0. Repeat validation
on the intended experiment versions before publication runs. Missing/null and mixed-type semantics and performance measurements are not covered.

## Generated pipeline smoke test

`tests/test_live_pipeline.py` exercises the production generator, loader, index setup,
connectors and concurrent runner using a unique test-owned database/scope. It generates
435 documents at SF=0.05, verifies identical loaded content, compares all eight queries,
and adds a Q4 instance whose location actually exists. Each backend then runs two
clients with one second of warm-up and three seconds of measurement. It independently
checks event pairing, admission boundaries, result counts, failure counts, throughput
and latency against the saved logs. Set `JSONBENCH_SMOKE_OUTPUT` to a fresh directory
to retain the dataset, queries, logs and report; otherwise pytest temporary storage is used.

The first observed pass completed 2,978 MongoDB and 115 Couchbase attempts without
errors/timeouts. These are smoke-test counts, not performance conclusions. The original
Q4 literal returned no rows; the additional present-location case returned one group.
Only the configured secondary indexes were created by the production loader.

```sh
JSONBENCH_LIVE=1 uv run --with ~/code/bondi --with-requirements requirements-dev.txt \
  python -m pytest tests/test_live_pipeline.py -q
```

Stop the isolated deployments without deleting them when finished:

```sh
uv run --project ~/code/bondi bondi stop jsonbench-live-mongo
uv run --project ~/code/bondi bondi stop jsonbench-live-cb
```

Use `bondi start NAME` to reuse them. Do not remove unrelated deployments.
