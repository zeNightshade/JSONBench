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
threads cannot forcibly terminate a stuck native driver. The CLI therefore spawns
an isolated benchmark process, with SDK connections created inside it. A parent
watchdog allows `startup_timeout_seconds` (default 60) until the shared worker
origin, then warm-up + measurement + `drain_timeout_seconds` (default 90).
The drain allowance also covers connection cleanup. At expiry the parent terminates
the child, waits up to one second, then kills it if needed (another one-second join).
It marks metadata aborted with a reason and removes any normal summary. Flushed
events remain; a final interrupted JSONL line may be incomplete. This bounds the
local benchmark process, not server-side cancellation of already submitted queries.

Direct calls to `benchmark.main` remain an in-process testing interface without a
watchdog; use `run_supervised` or the CLI for experiments. Parent termination or
machine failure can still leave incomplete metadata.

Default configuration: 60 seconds of warm-up, 180 seconds of measurement, 60-second
query timeout. Runs can take longer than 240 seconds because of draining.

## Artifacts

Each unique run directory contains:

- `info.json`: format, state, revision, tracked-change indicator, backend, worker
  count, phase durations, seed, query timeout, scale factor, concrete queries,
  Python/dependency versions, server version, destination database or bucket/scope,
  actual index definitions, optional dataset manifest/checksum, and actual duration.
- `events.jsonl`: started/completed records, worker and attempt identity, offsets,
  status, elapsed query duration, row count and error type/message.
- `summary.json`: metrics above, written only after successful runner completion.

Connection credentials are not copied to metadata. Error messages come from the
native driver and may contain query details; inspect before sharing logs.

Detailed database settings,
index readiness and validation on the paper database versions remain release
prerequisites tracked in TODO.md. A local manifest alone does not prove which data is loaded; the separate
verification report records the comparison performed for this run.

Database metadata is captured before worker startup; failure to inspect it aborts
the run rather than silently omitting it. MongoDB records collection index specs;
Couchbase records the Query service version and system:indexes entries for the
selected bucket/scope. These snapshots do not capture all server tuning settings
or replace the full loaded-document verification.

If `dataset_directory` is configured, full content verification occurs before the
worker origin. Its report is saved as `loaded_dataset_verification`; mismatches
abort the run. This pre-scan warms caches and uses the startup watchdog budget.
The report records Q4 visit selectivity without modifying its fixed predicate.
Keep data immutable: verification does not prevent subsequent writes.

## Full paper execution target

The author supplied the following paper environment: Amazon EC2 `m6a.xlarge`,
AMD EPYC 7R13 (2.6 GHz), 16 GB RAM, Red Hat Enterprise Linux 9.6,
a 128 GB EBS system volume, and a separate 250 GB EBS database-storage volume.
Full publication experiments must run on EC2; local runs are functional pilots,
not paper performance results. Before provisioning, specify EBS volume type,
provisioned IOPS/throughput, filesystem/mount settings, and database resource
settings. Confirm whether backend runs use one instance sequentially or identically
configured separate instances, and record the chosen arrangement.

Dates in the current dataset are ISO date-only strings (`YYYY-MM-DD`) in both
MongoDB and Couchbase. The loader does not convert them to BSON dates. None of the
eight workload queries operates on dates. A future date-query workload will need
an explicit shared contract for parsing, timezone, precision and date arithmetic.
