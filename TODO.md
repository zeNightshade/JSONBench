# JSONBench correctness and reproducibility TODO

Priority order reflects what must be resolved before a defensible experimental rerun.
Existing results must remain unchanged. Never interpret a missing timing as zero
latency or a successful completion. The current repository may differ from the
code that produced the historical logs.

## P0 — Repair analysis of existing results

- [x] Calculate latency from individual numeric query durations, not reciprocal throughput.
- [x] Report numeric and missing timings separately; show undefined latency when none are available.
- [x] Remove hard-coded throughput denominators and misleading throughput charts from legacy analysis.
- [x] Aggregate each backend independently; remove many-to-many observation merges.
- [x] Keep scale factor and concurrency settings separate in per-query summaries.
- [x] Read run duration and worker count from metadata; validate notebook mapping against metadata.
- [x] Add unit tests for averaging, null handling, metadata validation, and independent aggregation.
- [ ] Resolve what historical nulls represent with the experiment author; do not assume a logged error type.
- [ ] Identify the exact execution code used for the original experiments (the original checked-in MongoDB connector returned a cursor).

## P0 — Make execution measurements trustworthy before rerunning

- [x] Repair MongoDB execution: consume all results and return a consistently structured timed outcome.
- [x] Record success, timeout, and other errors explicitly, including elapsed time and error details.
- [x] Use a shared monotonic clock and common worker phase boundaries.
- [x] Implement explicit warm-up, measurement, and draining phases.
- [x] Define which attempts/completions belong to each metric; save actual phase timestamps.
- [x] Stop admissions at the deadline; handle late completions separately.
- [x] Add explicit driver per-query deadlines and document drain behaviour.
- [x] Add a CLI process-level startup/drain watchdog, retaining partial events and marking terminated runs aborted; native driver cleanup can exceed its requested deadline.
- [x] Calculate successful completion throughput from the measured interval, never from all records.
- [ ] Investigate Couchbase's systematic Q5–Q8 null timings at SF=10 and widespread nulls at larger scales.
- [x] Test timing boundaries, full cursor consumption, failures, timeouts, and draining with controlled fakes.

## P0 — Establish query correctness

- [x] Fix MongoDB projection's literal-string condition.
- [x] Fix Couchbase field-prefix rewriting (lstrip is not prefix removal).
- [x] Prevent translators from mutating input templates.
- [x] Unify and validate the sort representation.
- [x] Parameterise/escape SQL++ literal values and identifiers appropriately.
- [x] Reject unsupported expressions and null/missing predicates rather than silently compiling them.
- [ ] Define and validate a shared null/missing predicate contract.
- [ ] Define joins, duplicate handling, empty arrays, grouping, ordering, and result comparison semantics.
- [x] Validate all eight queries against independently calculated expected answers on small fixtures (MongoDB 8.0.16 and Couchbase Community 7.6.2, via BONDI).
- [x] Repeat small fixture/generated-data live validation on MongoDB 8.2.1 / Couchbase Community 8.0.0; edition confirmed to match the paper; run a representative-scale pilot separately.
- [x] Validate corresponding MongoDB and Couchbase results on a small generated dataset (SF=0.05); verify loaded documents and short concurrent-run metrics.
- [x] Preserve Q8's traveller-weighted tour-review average; update its description rather than changing joins.
- [x] Preserve Q4 itinerary-visit counting and Q1/Q7 semantics; update descriptions without changing operations.
- [x] Report Q4 matching tours/visits and visit selectivity from verified loaded data, preserving the fixed location and explicitly reporting zero matches.
- [ ] Correct the paper's Q3 operation table: the checked-in template does not unnest travellers.

## P1 — Reproducible datasets and experimental records

- [x] Seed every random generator and fix the date reference.
- [x] Remove global mutable generator state.
- [x] Generate a canonical dataset independently of database loading; load identical documents into both systems.
- [x] Save dataset checksums, sizes, generator configuration, and scale factor.
- [x] Compare all loaded documents against the artifact before configured dataset runs; persist verification counts, time and manifest checksum.
- [x] Validate the complete manifest, file sizes/counts, JSON records and unique document IDs before connecting or replacing collections.
- [x] Record code revision, dependency/server versions, native queries, and actual index definitions.
- [ ] Record database settings, seeds, query probabilities, timeout policy, and actual run duration.
- [x] Record attempt identity, worker identity, and start/finish offsets.
- [x] Persist observations incrementally and use unique run IDs.
- [x] Test reproducibility, repeated generation, and persistence under interruption.

## P1 — Configuration and database lifecycle

- [x] Make connection settings configurable; configuration parsing must not connect.
- [x] Separate domain-specific document creation from database connectors.
- [x] Make replacement of collections explicit.
- [x] Require a valid ownership marker before replacement; only an empty destination can be claimed automatically.
- [x] Close connections at pipeline exit and watch Couchbase secondary indexes after creation.
- [ ] Validate full loading/connection lifecycle against running servers, including newly created collection visibility to Couchbase Query.
- [x] Exercise both JSONBench query connectors against running servers for all eight fixture queries.

## P2 — Repeated experiments and publication analysis

- [ ] Define independent repetitions, seeds, run order, and cache policy.
- [ ] Run publication experiments on the specified EC2 m6a.xlarge/RHEL 9.6 environment; pin EBS and database resource settings (see measurement protocol).
- [ ] Generate figures from a recorded run manifest rather than manually selected directory names.
- [ ] Report failure rates, sample counts, latency distributions, and uncertainty across repetitions.
- [ ] Do not compare successful-only averages when the successful query mixes differ.
- [ ] Reconcile the methods and conclusions in the paper with validated new measurements.
- [ ] Decide whether to replace execution with BONDI as a separate change; keep benchmark semantics in this repository.
