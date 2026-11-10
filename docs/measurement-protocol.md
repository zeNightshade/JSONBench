# Measurement protocol (format version 2)

This is a new execution protocol, not a repair to the historical logs. Do not pool
new and old runs. The runner is closed-loop: each worker submits its next query
only after the previous query returns and its completion event is persisted.

## Boundaries and metrics

All worker threads share a monotonic origin, released by a barrier after startup.
`warmup_seconds` defines [0, warmup); `duration` is now the **measurement duration**,
not total run time. Admission ends at warmup + duration. There is no fixed cooldown:
in-flight queries drain under their configured driver query deadlines. No query is
admitted at or beyond the end boundary.

- Throughput counts successful finishes in [warmup, warmup + duration), divided by
  duration. A query admitted during warm-up that finishes during measurement counts.
- Mean successful latency uses successful queries admitted during measurement,
  including their late finishes. It excludes failures and is undefined without successes.
- Counts of measurement-admitted timeouts and errors accompany latency.
- Late completions are reported separately and never inflate window throughput.

Throughput and latency use intentionally different boundary cohorts. They need not
satisfy a steady-state identity in short, nonstationary runs. Preserve per-query
breakdowns, failure counts, and repetitions when interpreting them.

The event start offset is the admission observation, before writing its started
event. `time` measures the connector call's submission and full result consumption;
it excludes the event logging overhead. Finish offsets follow connector completion.
Synchronous event persistence adds think time between queries and can constrain the
load generator. Measure that overhead before using very short queries as a benchmark.

## Failure, deadlines, and draining

Database exceptions become structured success/timeout/error outcomes. Programming
errors abort scheduling and leave the run marked aborted. Completed events and
started events are flushed as they happen; an unmatched started event indicates an
unfinished or interrupted attempt, not a successful result. Aborted runs produce no
normal summary. Process crashes may leave `state=running`; this is incomplete.

MongoDB uses PyMongo's client operation deadline across cursor batches. Couchbase
passes an explicit SDK query timeout and fully consumes the iterator. Native SDK
cleanup and transport behaviour still determine exact cancellation latency: Python
threads cannot forcibly terminate a stuck native driver. This is **not** a hard
process-level watchdog. A strict hard drain bound remains pending.

Default configuration: 60 seconds of warm-up, 180 seconds of measurement, 60-second
query timeout. Runs can take longer than 240 seconds because of draining.

## Artifacts

Each unique run directory contains:

- `info.json`: format, state, revision, tracked-change indicator, backend, worker
  count, phase durations, seed, query timeout, scale factor, concrete queries,
  Python/dependency versions, optional dataset manifest/checksum, and actual duration.
- `events.jsonl`: started/completed records, worker and attempt identity, offsets,
  status, elapsed query duration, row count and error type/message.
- `summary.json`: metrics above, written only after successful runner completion.

Connection credentials are not copied to metadata. Error messages come from the
native driver and may contain query details; inspect before sharing logs.

Server versions, detailed database settings, verified loaded-dataset receipts,
index readiness, hard process deadlines, and live correctness checks remain release
prerequisites tracked in TODO.md. A local dataset manifest does not prove that dataset
is currently loaded in the server.
