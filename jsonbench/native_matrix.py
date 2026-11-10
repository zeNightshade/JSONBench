"""Run the matrix against sequential native systemd services on a dedicated host."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from jsonbench.matrix import atomic_json, locked

SERVICES = {"mongodb": "mongod", "couchbase": "couchbase-server"}


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def interrupted(signum, frame):
    raise KeyboardInterrupt(f"Received signal {signum}")


def execute(args, output, phase, env):
    with (output / f"{phase}.log").open("a") as log:
        process = subprocess.Popen(
            args, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True
        )
        try:
            with (output / "resources.jsonl").open("a") as observations:
                while process.poll() is None:
                    sample = {
                        "time": time.time(),
                        "phase": phase,
                        "meminfo": Path("/proc/meminfo").read_text(),
                        "loadavg": Path("/proc/loadavg").read_text(),
                        "diskstats": Path("/proc/diskstats").read_text(),
                        "services": command(
                            "systemctl",
                            "show",
                            *SERVICES.values(),
                            "-p",
                            "Id",
                            "-p",
                            "MemoryCurrent",
                            "-p",
                            "MemoryPeak",
                            "-p",
                            "CPUUsageNSec",
                            "-p",
                            "ActiveState",
                        ),
                    }
                    observations.write(json.dumps(sample) + "\n")
                    observations.flush()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        pass
            if process.returncode:
                raise RuntimeError(f"{phase} exited {process.returncode}; inspect its log")
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", default="experiments/paper-matrix.json")
    parser.add_argument("--connections", default="experiments/connections.example.json")
    parser.add_argument(
        "--credentials", default=str(Path.home() / ".config/jsonbench/credentials.json")
    )
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    signal.signal(signal.SIGTERM, interrupted)
    with locked(output / "orchestrator"):
        for service in SERVICES.values():
            if subprocess.run(["systemctl", "is-active", "--quiet", service]).returncode == 0:
                raise RuntimeError(
                    f"{service} already active; stop it before starting orchestration"
                )
        env = dict(os.environ)
        env["JSONBENCH_CB_PASSWORD"] = json.loads(Path(args.credentials).read_text())["couchbase"][
            "password"
        ]
        base = [sys.executable, "-m", "jsonbench.matrix"]
        common = ["--manifest", str(Path(args.manifest).resolve()), "--output", str(output)]
        status = {"state": "preparing", "pid": os.getpid(), "started_at": time.time()}
        active = None
        try:
            atomic_json(output / "native-status.json", status)
            execute(base + ["prepare"] + common, output, "prepare", env)
            for backend, service in SERVICES.items():
                active = service
                command("sudo", "-n", "/usr/local/sbin/jsonbench-native-service", backend, "start")
                status.update(state="running", backend=backend)
                atomic_json(output / "native-status.json", status)
                run_args = (
                    base
                    + ["run"]
                    + common
                    + ["--backend", backend, "--connections", str(Path(args.connections).resolve())]
                )
                if args.retry_failed:
                    run_args.append("--retry-failed")
                execute(run_args, output, backend, env)
                command("sudo", "-n", "systemctl", "stop", service)
                active = None
            status.update(state="complete", finished_at=time.time())
        except BaseException as error:
            status.update(state="failed", error=repr(error), finished_at=time.time())
            raise
        finally:
            try:
                if active:
                    command("sudo", "-n", "systemctl", "stop", active)
            finally:
                atomic_json(output / "native-status.json", status)


if __name__ == "__main__":
    main()
