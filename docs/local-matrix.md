# Local matrix rehearsal

The local manifest preserves all 108 paper-matrix cells and timings. It uses the
paper versions on fresh BONDI deployments named `jsonbench-matrix-mongo` and
`jsonbench-matrix-cb`, with ports 27031 and 9791/9793/11221 respectively.

Both container caps are 12 GiB, matching the proposed EC2 budget. MongoDB's
WiredTiger cache is 6 GiB. Couchbase has 4 GiB Data/bucket and 2 GiB Index quotas;
remaining memory supports query execution and other overhead. These are not the
larger JSON-Storm settings (MongoDB 24/10 GiB, Couchbase 32/20/4 GiB).

Use a dedicated output root and stop unrelated database containers first. Stopping
retains their data. The wrapper refuses to begin while other Docker containers
are running, prepares datasets, configures and checks quotas, runs MongoDB, stops
it, then runs Couchbase. It stops the active deployment on completion/failure and
retains both data directories. It does not restart unrelated deployments afterward.

```sh
PYTHONPATH=. uv run --python 3.11 --with ~/code/bondi \
  --with-requirements requirements-lock.txt python -u -m jsonbench.local_matrix \
  --output analysis/local-matrix-01
```

`local-status.json` records orchestration state. `state.json` records each matrix
attempt; `prepare.log`, `mongodb.log`, `couchbase.log` retain process output.
`resources.jsonl` samples Docker statistics approximately every 10 seconds and
`deployment-resources.json` records the selected images and memory quotas.
See the EC2 guide for resume semantics; use the same output and `--retry-failed`
only after investigating a failed/interrupted attempt. The wrapper accepts a
separate `--manifest` for a short acceptance run; publication queries are unchanged.

This run is a local rehearsal, not an EC2 hardware reproduction. Host CPU, Docker
virtualization, filesystem cache and storage still differ. Do not pool these
results with EC2 observations. Allow at least nine hours plus generation, loading,
verification and draining. Keep the machine awake and avoid other heavy workloads.
