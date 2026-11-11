# Native EC2 execution

The November 2026 runs use two dedicated Amazon Linux 2023 x86_64 hosts:
8 vCPUs / 16 GiB and 16 vCPUs / 32 GiB, each with one 100 GiB XFS root disk.
Both execute the complete 108-cell paper matrix, MongoDB first then Couchbase.
The runner executes on each server, not on the laptop. Results are separate per host.

MongoDB Community 8.2.1 and Couchbase Community 8.0.0 are native RPM installations.
Signed vendor repositories are disabled after installation to retain exact versions.
Each database service has a 12 GiB systemd MemoryMax and MemorySwapMax=0, no CPU
quota; MongoDB WiredTiger cache is 6 GiB, Couchbase Data/bucket is 4 GiB and Index
is 2 GiB. Thus the first comparison keeps database memory budgets fixed across
machines; it does not compare their maximum-memory performance. OS and runner share
host resources; filesystem cache and resource pressure must be considered in analysis.

Database ports are blocked on non-loopback interfaces by a persistent nftables
service. MongoDB binds localhost. Couchbase credentials stay in the remote
`~/.config/jsonbench/credentials.json` (0600), with `couchbase.username` and
`couchbase.password`. Never copy this file or the SSH private key into Git or result
archives. Transfer committed source using `git bundle`, never the entire laptop folder.

Install `infra/native-service.sh` root-owned mode0755 at
`/usr/local/sbin/jsonbench-native-service`. It checks the other backend is stopped,
sets THP before service startup (MongoDB always/defer+madvise and max_ptes_none=0;
Couchbase never/never), sets overcommit_memory=1 and swappiness=1, and waits for
readiness. No swap is configured. These settings follow the differing vendor THP
guidance; they are part of the protocol, not recovered historical paper settings.

- https://www.mongodb.com/docs/manual/administration/tcmalloc-performance/
- https://docs.couchbase.com/server/current/install/thp-disable.html

Use Python3.11 and `requirements-lock.txt`. After unit tests, run the small
`experiments/native-pilot.json` matrix first. It has two cells, one per backend,
SF1, two clients, two-second warmup and ten-second measurement. This is a pipeline
check, not full query-equivalence evidence or a performance result.

Run from a clean committed checkout:

```sh
/home/ec2-user/jsonbench-venv/bin/python -m jsonbench.native_matrix \
  --manifest experiments/native-pilot.json \
  --output /home/ec2-user/jsonbench-results/pilot-v1
# After inspection, use the default full manifest with a different output root:
/home/ec2-user/jsonbench-venv/bin/python -m jsonbench.native_matrix \
  --output /home/ec2-user/jsonbench-results/paper-v1
```

Launch using a systemd service with User=ec2-user, WorkingDirectory pointing to the
checkout, Restart=no and a generous TimeoutStopSec. Its cgroup keeps the job alive
after SSH disconnects and ensures cleanup on stop. The wrapper uses sudo for the
root-owned startup helper and service stops; the existing EC2 user has sudo rights.
Do not launch a second matrix on the same host. Inspect any failure before using
`--retry-failed`; it appends attempts and retains prior evidence. No automatic retry.
The wrapper always stops the active database when exiting normally or on handled
errors/signals. An OS crash or SIGKILL requires checking service state manually.

`native-status.json` reports orchestration state; `state.json` records individual
attempts; backend logs and `resources.jsonl` record progress and host/service usage.
Both services remain disabled for boot startup. The wrapper stops them at completion.
Capture CPU/kernel/package/storage metadata alongside each run. No Docker is used.

## Larger-host doubled-memory repeat: paper-memory24-v1

The repeat on `13.211.240.180` uses the same pinned benchmark revision
`3563e6e33da6ffa41c8b98cf9c98d0e07a8b0f73`, database versions and 108-cell
protocol as `paper-v1`. At the user's request, no pilot was run. Both database
service caps are 24 GiB with no swap; MongoDB WiredTiger cache is 12 GiB;
Couchbase Data/bucket quota is 8 GiB and Index quota is 4 GiB. The two databases
still run sequentially, MongoDB first. Query timeouts remain 60 seconds.

The new results root is `/home/ec2-user/jsonbench-results/paper-memory24-v1`,
and the systemd unit is `jsonbench-paper-memory24-v1`. The manifest lives in
that results root as `matrix-manifest.json`, with an absolute query-template path
into the pinned checkout. No benchmark-source change was required.

The new root's `setup/` directory contains original configuration backups,
nonsecret experiment metadata, verified Couchbase quota values and SHA256 hashes
of all 354 files in the original `paper-v1` root. Those hashes were checked again
after launch. Original result files are preserved; the active benchmark database
collections are reused and reloaded by the normal runner. Historical database logs
were already archived in `collected-logs/database-logs.tar.gz`.

Inspect progress with `systemctl status jsonbench-paper-memory24-v1`, the new
root's `native-status.json`, `state.json`, backend logs and `resources.jsonl`.
Do not resume against the old `paper-v1` root with these changed memory settings.
