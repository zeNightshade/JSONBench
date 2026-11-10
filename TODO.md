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
- [ ] Identify the exact execution code used for the original experiments (MongoDB currently returns a cursor).

## P0 — Make execution measurements trustworthy before rerunning

- [ ] Repair MongoDB execution: consume all results and return a consistently structured timed outcome.
- [ ] Record success, timeout, and other errors explicitly, including elapsed time and error details.
- [ ] Use a shared monotonic clock and common worker phase boundaries.
- [ ] Implement explicit warm-up, measurement, and draining phases.
- [ ] Define which attempts/completions belong to each metric; save actual phase timestamps.
- [ ] Stop admissions at the deadline; handle late completions separately.
- [ ] Define per-query deadlines and a bounded, documented drain policy.
- [ ] Calculate successful completion throughput from the measured interval, never from all records.
- [ ] Investigate Couchbase's systematic Q5–Q8 null timings at SF=10 and widespread nulls at larger scales.
- [ ] Test timing boundaries, full cursor consumption, failures, timeouts, and draining with controlled fakes.

## P0 — Establish query correctness

- [ ] Fix MongoDB projection's literal-string condition.
- [ ] Fix Couchbase field-prefix rewriting (lstrip is not prefix removal).
- [ ] Prevent translators from mutating input templates.
- [ ] Unify and validate the sort representation.
- [ ] Parameterise/escape SQL++ literal values and identifiers appropriately.
- [ ] Define null/missing predicate semantics and reject unsupported expressions.
- [ ] Define joins, duplicate handling, empty arrays, grouping, ordering, and result comparison semantics.
- [ ] Validate all eight queries against independently calculated expected answers on small fixtures.
- [ ] Validate corresponding MongoDB and Couchbase results on generated data.
- [ ] Clarify Q8's intended rating weighting.
- [ ] Correct the paper's Q3 operation table: the checked-in template does not unnest travellers.

## P1 — Reproducible datasets and experimental records

- [ ] Seed every random generator and fix the date reference.
- [ ] Remove global mutable generator state.
- [ ] Generate a canonical dataset independently of database loading; load identical documents into both systems.
- [ ] Save dataset checksums, sizes, generator configuration, and scale factor.
- [ ] Record code revision, dependency/database versions, native queries, and index definitions.
- [ ] Record database settings, seeds, query probabilities, timeout policy, and actual run duration.
- [ ] Record attempt identity, worker identity, and start/finish offsets.
- [ ] Persist observations incrementally and use unique run IDs.
- [ ] Test reproducibility, repeated generation, and persistence under interruption.

## P1 — Configuration and database lifecycle

- [ ] Remove hard-coded connections and credentials; configuration parsing must not connect.
- [ ] Separate domain-specific document creation from database connectors.
- [ ] Make replacement of collections explicit and isolate benchmark-owned data.
- [ ] Establish connection cleanup and index-readiness checks.

## P2 — Repeated experiments and publication analysis

- [ ] Define independent repetitions, seeds, run order, and cache policy.
- [ ] Generate figures from a recorded run manifest rather than manually selected directory names.
- [ ] Report failure rates, sample counts, latency distributions, and uncertainty across repetitions.
- [ ] Do not compare successful-only averages when the successful query mixes differ.
- [ ] Reconcile the methods and conclusions in the paper with validated new measurements.
- [ ] Decide whether to replace execution with BONDI as a separate change; keep benchmark semantics in this repository.
