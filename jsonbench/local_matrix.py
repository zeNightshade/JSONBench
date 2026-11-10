"""BONDI-managed local rehearsal; run one backend at a time and retain all data."""

import argparse
import base64
import hashlib
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
    suffix = hashlib.sha256(str(output).encode()).hexdigest()[:8]
    names = {
        backend: f"jsonbench-matrix-{suffix}-{backend}" for backend in ("mongodb", "couchbase")
    }
    manifest = str(Path(args.manifest).resolve())
    command = [sys.executable, "-m", "jsonbench.matrix"]
    status = {
        "state": "preparing",
        "started_at": time.time(),
        "pid": os.getpid(),
        "deployments": names,
    }
    connections = {
        "mongodb": {"uri": "mongodb://127.0.0.1:27031/", "database": "jsonbench_matrix"},
        "couchbase": {
            "uri": "couchbase://127.0.0.1:11221?network=external",
            "username": "Administrator",
            "password_env": "JSONBENCH_CB_PASSWORD",
            "bucket": "jsonbench_matrix",
            "scope": "benchmark",
        },
    }
    with locked(output / "orchestrator"):
        for deployment in list_deployments():
            if deployment.name in names.values():
                deployment.stop()
        running = subprocess.check_output(
            ["docker", "ps", "--format", "{{.Names}}"], text=True
        ).strip()
        if running:
            raise RuntimeError(
                f"Stop other containers before starting an isolated matrix: {running}"
            )
        atomic_json(output / "local-status.json", status)
        atomic_json(output / "connections.json", connections)
        active = None
        resources = {}
        try:
            execute(
                command + ["prepare", "--manifest", manifest, "--output", str(output)],
                output,
                "prepare",
            )
            for backend in ("mongodb", "couchbase"):
                status.update(state="starting", backend=backend)
                atomic_json(output / "local-status.json", status)
                if backend == "mongodb":
                    active = deploy_mongodb(
                        names[backend],
                        port=27031,
                        version="8.2.1",
                        memory_limit_mb=12288,
                        wiredtiger_cache_size_gb=6,
                    )
                    if active.memory_limit_mb != 12288 or active.wiredtiger_cache_size_gb != 6:
                        raise RuntimeError("MongoDB saved resource settings differ")
                    resources[backend] = {
                        "image": active.image,
                        "container_mib": active.memory_limit_mb,
                        "cache_gib": active.wiredtiger_cache_size_gb,
                    }
                    env = dict(os.environ)
                else:
                    # Create Couchbase only when its phase begins: no unnecessary pre-run restart.
                    active = deploy_couchbase(
                        names[backend],
                        management_port=9791,
                        query_port=9793,
                        kv_port=11221,
                        version="8.0.0",
                        edition="community",
                        bucket="jsonbench_matrix",
                        memory_limit_mb=12288,
                    )
                    management(
                        active, "/pools/default", {"memoryQuota": 4096, "indexMemoryQuota": 2048}
                    )
                    management(
                        active, "/pools/default/buckets/jsonbench_matrix", {"ramQuotaMB": 4096}
                    )
                    quotas = management(active, "/pools/default")
                    bucket = management(active, "/pools/default/buckets/jsonbench_matrix")
                    if quotas["memoryQuota"] != 4096 or quotas["indexMemoryQuota"] != 2048:
                        raise RuntimeError("Couchbase service quotas do not match")
                    if bucket["quota"]["ram"] != 4096 * 1024**2:
                        raise RuntimeError("Couchbase bucket quota does not match")
                    connector = Couchbase(
                        uri=active.uri,
                        username=active.username,
                        password=active.password,
                        bucket=active.bucket,
                        scope="benchmark",
                    )
                    try:
                        if "benchmark" not in {
                            scope.name for scope in connector.coll_mgr.get_all_scopes()
                        }:
                            connector.coll_mgr.create_scope("benchmark")
                    finally:
                        connector.close()
                    resources[backend] = {
                        "image": active.image,
                        "container_mib": active.memory_limit_mb,
                        "data_mib": quotas["memoryQuota"],
                        "index_mib": quotas["indexMemoryQuota"],
                        "bucket_bytes": bucket["quota"]["ram"],
                    }
                    env = dict(os.environ, JSONBENCH_CB_PASSWORD=active.password)
                atomic_json(output / "deployment-resources.json", resources)
                status.update(state="running")
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
                active.stop()
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
