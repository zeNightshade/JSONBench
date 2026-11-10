"""Conservative offline analysis of legacy name/time logs.

These logs have no observation timestamps or structured status. Numeric timings
are observations, not proof of correct query answers. Missing timings remain
unclassified; exact measurement-window throughput cannot be recovered.
"""

import json
import math
from pathlib import Path
from statistics import mean, median


def summarize_records(records):
    """Summarize durations without replacing missing observations with zero."""
    records = list(records)
    times = []
    for record in records:
        value = record["time"]
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Timing must be a number or null")
        if not math.isfinite(value) or value < 0:
            raise ValueError("Timing must be finite and nonnegative")
        times.append(value)

    return {
        "attempts": len(records),
        "numeric_timings": len(times),
        "missing_timings": len(records) - len(times),
        "mean_seconds": mean(times) if times else None,
        "median_seconds": median(times) if times else None,
        "throughput_qps": None,
    }


def summarize_run(path, *, expected_workers=None):
    """Read one run, retaining metadata and independent per-query summaries."""
    path = Path(path)
    info = json.loads((path / "info.json").read_text())
    workers = json.loads((path / "results.json").read_text())
    count = info["workers"]
    if type(count) is not int or count <= 0 or len(workers) != count:
        raise ValueError("Worker metadata does not match result groups")
    if expected_workers is not None and expected_workers != count:
        raise ValueError("Selected concurrency does not match run metadata")
    duration = info["duration"]
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration <= 0
    ):
        raise ValueError("Configured duration must be positive and finite")

    groups = {}
    records = []
    for worker in workers:
        if not isinstance(worker, list):
            raise TypeError("Each worker must contain a list of observations")
        for record in worker:
            if not isinstance(record["name"], str):
                raise TypeError("Query name must be a string")
            records.append(record)
            groups.setdefault(record["name"], []).append(record)

    return {
        "run_id": path.name,
        "workers": count,
        "configured_duration_seconds": duration,
        **summarize_records(records),
        "queries": {name: summarize_records(rows) for name, rows in sorted(groups.items())},
    }
