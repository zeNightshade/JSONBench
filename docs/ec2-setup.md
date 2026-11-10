# EC2 execution guide

**Current deployment:** see [Native EC2 execution](ec2-native.md) for the two
professor-provided hosts. The Docker/two-volume provisioning below is the earlier
setup and is not used for these native runs.

## Fixed initial protocol

`experiments/paper-matrix.json` expands to 108 runs: MongoDB 8.2.1 and Couchbase
Community 8.0.0 × SF 10/100/200 × 2/4/8/16/32/64 clients × three repetitions.
All eight queries have probability 1/8. Dataset seed is 42 for every repetition;
workload selection seeds are 42/43/44. These are repeated executions of the same
artifact, not three independently generated datasets. Client ordering reverses
for repetition two. Complete MongoDB before starting Couchbase.

Paper timings are 60 seconds warm-up, 180 measurement and 60 cooldown. The repaired
runner first drains outstanding queries (60-second driver timeout, 90-second hard
drain allowance) and then waits 60 seconds before the next run. Full content
verification precedes every run, so this is a pre-scanned/warmed workload, not a
cold-cache study. Startup/verification has a one-hour watchdog allowance. These
choices must be described in the revised paper; the old fixed 300-second execution
is not reproduced. Nine hours is the nominal schedule excluding preparation,
verification and draining. Extra scale factors require a new manifest/output root.

## Provision one host

Use Sydney (`ap-southeast-2`) by default, or Melbourne (`ap-southeast-4`). The
script discovers an official Red Hat RHEL 9.6 x86_64 AMI and a default subnet with
m6a.xlarge offerings. It requires a default VPC/subnet and AWS CLI credentials.
It creates one on-demand m6a.xlarge, encrypted gp3 volumes (128 GiB root, 250 GiB
separate data disk, each 3,000 IOPS/125 MiB/s), IMDSv2, and SSH access from one /32.
Database ports are never publicly exposed. No IAM credentials are copied to EC2.

```sh
python infra/deploy_ec2.py --ssh-cidr YOUR_PUBLIC_IPV4/32 --state /private/path/ec2.json
# Same command with --launch provisions the displayed configuration.
```

The state file records the instance, volumes, security group and private-key path.
It refuses to overwrite existing state; after an interrupted or rejected deployment inspect
that state and AWS tags before doing anything else. Do not run another launch
blindly. Keys are generated under ~/.ssh. There is no automatic termination.
The data disk is retained on instance termination; the root disk is deleted.
Stopping the instance retains both disks and their charges.

Bootstrap mounts the new data disk at /data, places Docker storage there, and
installs Docker/Compose, Python 3.11, uv, git, tmux and sysstat. Check completion:

```sh
ssh -i KEY ec2-user@PUBLIC_IP
sudo cloud-init status --wait
sudo tail -60 /var/log/jsonbench-bootstrap.log
cat /etc/redhat-release
lsblk -f
df -h /data
docker version
docker compose version
```

Do not upgrade the OS minor version during the study. Record the AMI, package
versions, kernel, CPU, image digests, EBS configuration and filesystem settings.
The expected CPU model must be verified on the actual host, not inferred from
instance type alone. AWS installation packages may change; freeze the resulting
host image or retain the complete package inventory before publication runs.

## Install the exact benchmark revision

Copy this checkout at its committed feature-branch revision, including the
experiments/ and infra/ directories. Do not copy historical results or local pilot
artifacts. Work under /data/JSONBench. Use the frozen dependencies:

```sh
uv venv --python 3.11
uv pip sync requirements-lock.txt
. .venv/bin/activate
python -m pytest tests -q
mkdir -p /data/jsonbench-results
python -m jsonbench.matrix plan --output /data/jsonbench-results/paper-v1
python -m jsonbench.matrix prepare --output /data/jsonbench-results/paper-v1
```

Keep the repository clean: the runner pins the Git revision, manifest, templates
and dependency versions. Do not edit them mid-matrix. The output lock prevents two
matrix invocations sharing a root. Keep only one matrix root active per host.

## Database setup and sequential execution

`infra/compose.yaml` pins the images and places both data directories on /data.
Each database gets a 12 GiB container cap; MongoDB gets a 6 GiB WiredTiger cache.
These are explicit new protocol choices, not settings recovered from the paper.
Couchbase initialization below uses a 4 GiB Data quota, 2 GiB Index quota and
4 GiB bucket quota. Confirm that the largest dataset fits before the full run;
inspect residency, disk spills and resource pressure rather than silently resizing.

```sh
docker compose -f infra/compose.yaml up -d mongodb
# Wait until mongosh --eval 'db.adminCommand({ping:1})' succeeds inside the container.
python -m jsonbench.matrix run --backend mongodb --output /data/jsonbench-results/paper-v1
docker compose -f infra/compose.yaml stop mongodb

docker compose -f infra/compose.yaml up -d couchbase
read -s -p 'Couchbase password: ' JSONBENCH_CB_PASSWORD
export JSONBENCH_CB_PASSWORD
# Initialize this new container once (not on resume):
docker compose -f infra/compose.yaml exec -T -e CB_PASSWORD="$JSONBENCH_CB_PASSWORD" couchbase \
  sh -c '/opt/couchbase/bin/couchbase-cli cluster-init -c 127.0.0.1 \
  --cluster-username Administrator --cluster-password "$CB_PASSWORD" \
  --services data,index,query --cluster-ramsize 4096 --cluster-index-ramsize 2048'
docker compose -f infra/compose.yaml exec -T -e CB_PASSWORD="$JSONBENCH_CB_PASSWORD" couchbase \
  sh -c '/opt/couchbase/bin/couchbase-cli bucket-create -c 127.0.0.1 \
  -u Administrator -p "$CB_PASSWORD" --bucket jsonbench_paper \
  --bucket-type couchbase --bucket-ramsize 4096 --bucket-replica 0 --wait'
```

Create the empty `benchmark` scope once using the SDK:

```sh
python - <<'PY'
import os
from jsonbench.database_connectors.couchbase import Couchbase
c = Couchbase(password=os.environ['JSONBENCH_CB_PASSWORD'], bucket='jsonbench_paper', scope='benchmark')
try:
    c.coll_mgr.create_scope('benchmark')
finally:
    c.close()
PY
python -m jsonbench.matrix run --backend couchbase --output /data/jsonbench-results/paper-v1
docker compose -f infra/compose.yaml stop couchbase
```

The runner checks the other backend's local standard port is closed before each
cell. This is an additional guard, not a substitute for stopping the other container;
custom ports/remote deployments are outside this guide. The loader owns only its
four benchmark collections and marker; it reloads once per scale within a phase.
On resume it reloads the first pending scale, then verifies every run. New destinations
must be empty. Never use production databases.

## Resume, failures and inspection

Run inside tmux, keeping stdout/stderr in a log. Reuse the same command/output root
on resume. A cell is skipped only if its state is complete and its run artifacts
exist. Native timeouts/errors are valid recorded outcomes, not infrastructure
failures: a completed run is not automatically a successful workload.

Interrupted or failed cells stop the phase. Inspect state.json and the attempt's
info/events first. Confirm there are no orphan benchmark processes or still-running
server queries, then rerun with `--retry-failed` to create a new attempt. Never
rewrite or discard the original failure. A process killed between run completion
and state persistence needs explicit retry; the runner does not guess completion.
Plan, template, dependency, revision or connection changes require a new output root.
If dataset generation is interrupted, move the incomplete dataset directory aside
for inspection before rerunning preparation; it will never overwrite partial files.
Cooldown deadlines survive resume. Dataset files must remain immutable.

Preserve plan.json, state.json, datasets/manifests, all attempts, console logs,
server logs and resource observations. Before publication execution, run an EC2
acceptance test and check largest-scale capacity. Collect sysstat/iostat and
Docker memory/OOM data throughout; recording intervals and tools must stay fixed.
Export artifacts to an agreed S3 bucket or local durable storage before termination.
S3 destination/IAM permissions and automated resource collection are not configured
by this initial runner. It also does not yet generate publication figures.

## Validation status

The matrix/resume logic and AWS request construction have local unit coverage;
Compose and bootstrap shell syntax are validated. On 2026-11-10 the Sydney launch
was rejected by AWS because the account was blocked pending account verification.
No instance was created, so bootstrap and EC2 end-to-end acceptance are still
unverified. Resolve that account restriction before attempting the real matrix.
The attempt's private local state records its retained key pair and security group;
reuse or explicitly clean up those resources rather than duplicating them.
