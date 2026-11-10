"""Closed-loop execution with shared boundaries and incremental event persistence."""

import hashlib
import json
import math
import platform
import random
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from uuid import uuid4


def validate_probabilities(queries, probabilities):
    if not queries or len(queries) != len(probabilities):
        raise ValueError("One probability is required per query")
    if any(
        isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or p < 0
        for p in probabilities
    ):
        raise ValueError("Probabilities must be finite and nonnegative")
    if not math.isclose(sum(probabilities), 1.0):
        raise ValueError("Probabilities must sum to one")


def worker_loop(
    database,
    queries,
    probabilities,
    *,
    worker,
    seed,
    origin,
    warmup,
    duration,
    timeout,
    emit,
    clock=time.perf_counter,
    stop=None,
):
    rng = random.Random(seed + worker)
    end = warmup + duration
    sequence = 0
    while True:
        start = clock() - origin
        if start >= end or (stop is not None and stop.is_set()):
            return
        query = rng.choices(queries, weights=probabilities, k=1)[0]
        attempt = {
            "attempt_id": f"{worker}:{sequence}",
            "worker": worker,
            "name": query["name"],
            "start_seconds": start,
        }
        emit({**attempt, "event": "started"})
        result = database.query(
            query["primary_collection"], query["query"], timeout_seconds=timeout
        )
        finish = clock() - origin
        if result["status"] not in {"success", "timeout", "error"}:
            raise ValueError("Invalid connector outcome")
        emit(
            {
                **attempt,
                **result,
                "event": "completed",
                "finish_seconds": finish,
                "phase_started": "warmup" if start < warmup else "measurement",
            }
        )
        sequence += 1


def summarize_events(events, warmup, duration):
    """Throughput counts successes finishing inside [warmup, warmup+duration).

    Latency uses measurement-admitted attempts, including their drained finishes.
    Failures and boundary-crossing successes remain separately countable.
    """
    end = warmup + duration
    successes = timeouts = errors = completed = in_window = late = 0
    total_latency = 0.0
    for record in events:
        if record["event"] != "completed":
            continue
        finish = record["finish_seconds"]
        if record["status"] == "success" and warmup <= finish < end:
            in_window += 1
        late += finish >= end
        if not warmup <= record["start_seconds"] < end:
            continue
        completed += 1
        if record["status"] == "success":
            successes += 1
            total_latency += record["time"]
        elif record["status"] == "timeout":
            timeouts += 1
        else:
            errors += 1
    return {
        "successful_completion_throughput_qps": in_window / duration,
        "measurement_success_mean_seconds": total_latency / successes if successes else None,
        "measurement_attempts_completed": completed,
        "measurement_successes": successes,
        "measurement_timeouts": timeouts,
        "measurement_errors": errors,
        "late_completions": late,
    }


def main(config, queries, *, run_path=None, on_start=None):
    settings = config.settings
    probabilities = config.get_query_sel_prob()
    validate_probabilities(queries, probabilities)
    database = config.get_database()
    warmup, duration = settings["warmup_seconds"], settings["duration"]
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:12]
    path = Path(run_path) if run_path is not None else (
        Path(settings.get("results_directory", "jsonbench/results"))
        / config.get_database_type()
        / run_id
    )
    path.mkdir(parents=True, exist_ok=run_path is not None)
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = None
    # Credentials are deliberately not copied into result metadata.
    info = {
        "format_version": 2,
        "state": "running",
        "revision": revision,
        "workers": config.get_workers(),
        "warmup_seconds": warmup,
        "measurement_seconds": duration,
        "seed": settings["seed"],
        "query_timeout_seconds": settings["query_timeout_seconds"],
        "startup_timeout_seconds": settings.get("startup_timeout_seconds", 60),
        "drain_timeout_seconds": settings.get("drain_timeout_seconds", 90),
        "scale_factor": config.get_scale_factor(),
        "probabilities": probabilities,
        "queries": queries,
        "backend": config.get_database_type(),
    }
    info["database_metadata"] = database.experiment_metadata()
    info["python_version"] = platform.python_version()
    info["dependencies"] = {}
    for package in ("pymongo", "couchbase", "Faker"):
        try:
            info["dependencies"][package] = version(package)
        except PackageNotFoundError:
            pass
    dataset_manifest = Path(settings.get("dataset_directory", "datasets")) / "manifest.json"
    if dataset_manifest.is_file():
        content = dataset_manifest.read_bytes()
        info["dataset_manifest_sha256"] = hashlib.sha256(content).hexdigest()
        info["dataset_manifest"] = json.loads(content)
    try:
        info["tracked_changes"] = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=no"], text=True
            ).strip()
        )
    except (OSError, subprocess.CalledProcessError):
        info["tracked_changes"] = None
    (path / "info.json").write_text(json.dumps(info, indent=2))
    lock = threading.Lock()
    stop = threading.Event()
    origin = None

    def release():
        nonlocal origin
        origin = time.perf_counter()
        if on_start is not None:
            on_start(origin)

    barrier = threading.Barrier(config.get_workers(), action=release)
    with (path / "events.jsonl").open("w") as file:

        def emit(event):
            with lock:
                file.write(json.dumps(event, allow_nan=False) + "\n")
                file.flush()

        def run(worker):
            barrier.wait()
            try:
                worker_loop(
                    database,
                    queries,
                    probabilities,
                    worker=worker,
                    seed=settings["seed"],
                    origin=origin,
                    warmup=warmup,
                    duration=duration,
                    timeout=settings["query_timeout_seconds"],
                    emit=emit,
                    stop=stop,
                )
            except BaseException:
                stop.set()
                raise

        try:
            with ThreadPoolExecutor(max_workers=config.get_workers()) as pool:
                futures = [pool.submit(run, w) for w in range(config.get_workers())]
                for future in futures:
                    future.result()
            info["state"] = "complete"
        except BaseException:
            stop.set()
            info["state"] = "aborted"
            raise
        finally:
            info["actual_seconds"] = time.perf_counter() - origin if origin is not None else None
            (path / "info.json").write_text(json.dumps(info, indent=2))
    with (path / "events.jsonl").open() as file:
        summary = summarize_events((json.loads(line) for line in file), warmup, duration)
    (path / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"Saved run to {path}")
    return path
