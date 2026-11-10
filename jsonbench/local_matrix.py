"""BONDI-managed local rehearsal; run one backend at a time and retain all data."""

import argparse
import base64
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from jsonbench.matrix import atomic_json, locked


def management(deployment, endpoint, settings=None):
    token = base64.b64encode(f"{deployment.username}:{deployment.password}".encode()).decode()
    request = Request(
        deployment.console_url.rstrip("/") + endpoint,
        data=urlencode(settings).encode() if settings is not None else None,
        headers={"Authorization": f"Basic {token}"},
    )
    with urlopen(request, timeout=30) as response:
        content = response.read()
        return json.loads(content) if content else None


def execute(command, output, phase, env=None):
    with (output / f"{phase}.log").open("a") as log:
        process = subprocess.Popen(
            command, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True
        )
        try:
            with (output / "resources.jsonl").open("a") as observations:
                while process.poll() is None:
                    result = subprocess.run(
                        ["docker", "stats", "--no-stream", "--format", "{{json .}}"],
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    observations.write(
                        json.dumps(
                            {
                                "time": time.time(),
                                "phase": phase,
                                "docker_stats": result.stdout.strip(),
                            }
                        )
                        + "\n"
                    )
                    observations.flush()
                    time.sleep(10)
            if process.returncode:
                raise RuntimeError(
                    f"{phase} failed with exit {process.returncode}; inspect its log"
                )
        except BaseException:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise


def main():
    from bondi.deployment import deploy_couchbase, deploy_mongodb, get_deployment, list_deployments

    from jsonbench.database_connectors.couchbase import Couchbase

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", default="experiments/local-matrix.json")
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    mongo_name, cb_name = "jsonbench-matrix-mongo", "jsonbench-matrix-cb"
    manifest = str(Path(args.manifest).resolve())
    command = [sys.executable, "-m", "jsonbench.matrix"]
    status = {"state": "preparing", "started_at": time.time(), "pid": os.getpid()}
    # Separate orchestration lock; matrix subprocesses acquire the output lock themselves.
    with locked(output / "orchestrator"):
        for deployment in list_deployments():
            if deployment.name in (mongo_name, cb_name):
                deployment.stop()
        running = subprocess.check_output(
            ["docker", "ps", "--format", "{{.Names}}"], text=True
        ).strip()
        if running:
            raise RuntimeError(
                f"Stop other containers before starting an isolated matrix: {running}"
            )
        atomic_json(output / "local-status.json", status)
        active = None
        try:
            execute(
                command + ["prepare", "--manifest", manifest, "--output", str(output)],
                output,
                "prepare",
            )
            couch = deploy_couchbase(
                cb_name,
                management_port=9791,
                query_port=9793,
                kv_port=11221,
                version="8.0.0",
                edition="community",
                bucket="jsonbench_matrix",
                memory_limit_mb=12288,
            )
            active = couch
            management(couch, "/pools/default", {"memoryQuota": 4096, "indexMemoryQuota": 2048})
            management(couch, "/pools/default/buckets/jsonbench_matrix", {"ramQuotaMB": 4096})
            quotas = management(couch, "/pools/default")
            bucket = management(couch, "/pools/default/buckets/jsonbench_matrix")
            if quotas["memoryQuota"] != 4096 or quotas["indexMemoryQuota"] != 2048:
                raise RuntimeError("Couchbase service quotas do not match")
            if bucket["quota"]["ram"] != 4096 * 1024**2:
                raise RuntimeError("Couchbase bucket quota does not match")
            connector = Couchbase(
                uri=couch.uri,
                username=couch.username,
                password=couch.password,
                bucket=couch.bucket,
                scope="benchmark",
            )
            try:
                if "benchmark" not in {scope.name for scope in connector.coll_mgr.get_all_scopes()}:
                    connector.coll_mgr.create_scope("benchmark")
            finally:
                connector.close()
            couch.stop()
            active = None
            mongo = deploy_mongodb(
                mongo_name,
                port=27031,
                version="8.2.1",
                memory_limit_mb=12288,
                wiredtiger_cache_size_gb=6,
            )
            active = mongo
            if mongo.memory_limit_mb != 12288 or mongo.wiredtiger_cache_size_gb != 6:
                raise RuntimeError("MongoDB saved resource settings differ")
            resources = {
                "mongodb": {
                    "image": mongo.image,
                    "container_mib": mongo.memory_limit_mb,
                    "cache_gib": mongo.wiredtiger_cache_size_gb,
                },
                "couchbase": {
                    "image": couch.image,
                    "container_mib": couch.memory_limit_mb,
                    "data_mib": quotas["memoryQuota"],
                    "index_mib": quotas["indexMemoryQuota"],
                    "bucket_bytes": bucket["quota"]["ram"],
                },
            }
            atomic_json(output / "deployment-resources.json", resources)
            connections = {
                "mongodb": {"uri": mongo.uri, "database": "jsonbench_matrix"},
                "couchbase": {
                    "uri": couch.uri,
                    "username": couch.username,
                    "password_env": "JSONBENCH_CB_PASSWORD",
                    "bucket": couch.bucket,
                    "scope": "benchmark",
                },
            }
            atomic_json(output / "connections.json", connections)
            env = dict(os.environ, JSONBENCH_CB_PASSWORD=couch.password)
            for backend, deployment in [("mongodb", mongo), ("couchbase", couch)]:
                active = deployment
                deployment.start()
                status.update(state="running", backend=backend)
                atomic_json(output / "local-status.json", status)
                run_command = command + [
                    "run",
                    "--manifest",
                    manifest,
                    "--output",
                    str(output),
                    "--backend",
                    backend,
                    "--connections",
                    str(output / "connections.json"),
                ]
                if args.retry_failed:
                    run_command.append("--retry-failed")
                execute(run_command, output, backend, env)
                deployment.stop()
                active = None
            status.update(state="complete", finished_at=time.time())
        except BaseException as error:
            status.update(state="failed", error=str(error), finished_at=time.time())
            raise
        finally:
            if active is not None:
                get_deployment(active.name).stop()
            atomic_json(output / "local-status.json", status)


if __name__ == "__main__":
    main()
