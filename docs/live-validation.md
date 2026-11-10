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

The fixture pins the retained Q4/Q8 semantics. Q4 counts itinerary visits; Q8 joins
all reviews to all travellers within a tour. The workload descriptions now reflect
these operations; see [query semantics](query-templates.md).

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

## Paper-version validation (2026-11-10)

BONDI 0.1.9 deployed separate MongoDB 8.2.1 and Couchbase Community 8.0.0
instances, named `jsonbench-paper-mongo` and `jsonbench-paper-cb`. MongoDB uses
port 27030, a 1024 MiB container cap and 0.25 GiB WiredTiger cache. Couchbase
uses ports 9691/9693/11220, bucket `jsonbench_paper`, and a 4096 MiB container
cap. These are local correctness settings, not a reproduction of paper hardware.
The paper uses Couchbase Community 8.0.0, confirmed by the author; the deployed
edition and version match.

All 18 fixture checks passed. The generated SF=0.05 test also passed on these
versions: 435 documents verified, all eight query results equivalent, and 2,964
MongoDB / 122 Couchbase attempts with no errors or timeouts. Two clients ran for
one second of warm-up and three seconds of measurement per backend. The original
Q4 predicate matched nothing; a separate extra fixture query exercised a present
location. Production query semantics remain unchanged. These short runs do not
support performance comparisons or establish behaviour at paper scale.

The retained local report is `analysis/paper-versions-smoke-02/report.json`.
The earlier `smoke-01` generated run used the old deployments because that test
hard-coded their names; the test now honours both deployment environment variables
and includes observed server versions in its report.

```sh
JSONBENCH_LIVE=1 \
JSONBENCH_MONGO_DEPLOYMENT=jsonbench-paper-mongo \
JSONBENCH_CB_DEPLOYMENT=jsonbench-paper-cb \
uv run --with ~/code/bondi --with-requirements requirements-dev.txt \
  python -m pytest tests/test_live_equivalence.py tests/test_live_pipeline.py -q
```

## Representative-scale local pilot (SF=10)

On 2026-11-10, the matching paper-version deployments loaded and verified 87,000
identical generated documents (10,000 users, 2,000 tours, 50,000 bookings and
25,000 reviews; seed 42). The unchanged eight queries each completed successfully
on both systems with matching row counts. Row counts alone do not establish full
result equivalence at this scale; that was checked separately on the small fixtures.
Q4 returned zero rows for its existing location literal.

Each backend then ran two clients with 10 seconds of warm-up and 30 seconds of
measurement, 60-second query deadlines, and a 90-second drain allowance. All
197 MongoDB and 24 Couchbase completed attempts succeeded, with no timeouts/errors.
The short random Couchbase run did not select Q8, so a separate targeted check
submitted two simultaneous Q8 queries: both returned 56,910 rows successfully in
about 38.5 seconds. Their finishes were drained beyond a one-second admission
window; that check is not a throughput measurement.

Artifacts and the pilot scripts are retained locally in `analysis/pilot-s10-01/`,
including `report.json`, `resources.json`, dataset, generated queries and event logs.
MongoDB had a 1 GiB container cap / 0.25 GiB cache; Couchbase had a 4 GiB cap.
Other databases were running on the host. Full data verification pre-scanned the
collections. These conditions differ from the target EC2 setup, so these timings
must not be used as paper performance results. The pilot does not reproduce or
explain the original missing Couchbase timings.
