"""Process isolation for the CLI; never share live SDK clients across processes."""

import json
import multiprocessing
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from jsonbench.benchmark.benchmark import main
from jsonbench.config_loader.config_loader import ConfigLoader


def _execute(settings, queries, path, channel):
    config = ConfigLoader.__new__(ConfigLoader)
    config.settings = settings
    config.database_type = settings["database"]
    config.database = None
    try:
        main(config, queries, run_path=path, on_start=lambda origin: channel.send(origin))
    finally:
        config.close()
        channel.close()


def _abort(path, reason):
    info_path = path / "info.json"
    try:
        info = json.loads(info_path.read_text())
    except (OSError, ValueError):
        info = {"format_version": 2}
    info.update(state="aborted", abort_reason=reason)
    temporary = path / "info.json.tmp"
    temporary.write_text(json.dumps(info, indent=2))
    temporary.replace(info_path)
    (path / "summary.json").unlink(missing_ok=True)


def _monitor(process, channel, *, startup, run_budget):
    deadline = time.perf_counter() + startup
    started = False
    while process.is_alive():
        if not started and channel.poll():
            try:
                origin = channel.recv()
            except EOFError:
                pass
            else:
                deadline = origin + run_budget
                started = True
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return "drain_watchdog" if started else "startup_watchdog"
        process.join(min(remaining, 0.05))
    return None if process.exitcode == 0 else "worker_process_failed"


def run_supervised(config, queries):
    """Run with bounded startup and drain; return a path only on clean process exit."""
    settings = dict(config.settings)
    path = (
        Path(settings.get("results_directory", "jsonbench/results"))
        / config.get_database_type()
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:12])
    )
    path.mkdir(parents=True, exist_ok=False)
    (path / "info.json").write_text(json.dumps({"format_version": 2, "state": "starting"}))
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_execute, args=(settings, queries, path, sender))
    reason = None
    try:
        process.start()
        sender.close()
        reason = _monitor(
            process, receiver,
            startup=settings.get("startup_timeout_seconds", 60),
            run_budget=settings["warmup_seconds"] + settings["duration"]
            + settings.get("drain_timeout_seconds", 90),
        )
    except BaseException:
        reason = "supervisor_interrupted"
        raise
    finally:
        # Termination is followed by a bounded grace period and a forced kill.
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
                process.join(1)
            if process.is_alive():
                process.kill()
                process.join(1)
        receiver.close()
        sender.close()
        if reason:
            _abort(path, reason)
    if reason:
        raise RuntimeError(f"Benchmark aborted ({reason}); partial artifacts: {path}")
    return path
