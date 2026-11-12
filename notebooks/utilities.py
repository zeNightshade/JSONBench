"""Load matrix artifacts and prepare validated data for result_analysis.ipynb."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.cbook import boxplot_stats


def matrix_paths(matrix_name):
    """Resolve a run directory and its figure destination from either notebook cwd."""
    root = next(p for p in (Path.cwd(), *Path.cwd().parents) if (p / "jsonbench/matrix.py").exists())
    data = root / "analysis" / matrix_name
    if not (data / "plan.json").is_file():
        candidates = sorted(str(p.parent.relative_to(root / "analysis")) for p in data.glob("*/plan.json"))
        hint = f" Available runs: {', '.join(candidates)}." if candidates else " Check the experiment name and result files."
        raise FileNotFoundError(f"No plan.json directly inside {data}.{hint} Set MATRIX_NAME to the run directory.")
    out = data / "figures"
    out.mkdir(parents=True, exist_ok=True)
    return data, out


def load_matrix(data):
    """Validate completions and compute the documented measurement cohorts."""
    DATA = Path(data)
    plan = json.loads((DATA / "plan.json").read_text())
    state = json.loads((DATA / "state.json").read_text())
    rows, event_rows = [], []
    for cell in plan["cells"]:
        history = state["attempts"].get(cell["id"], [])
        assert history and history[-1]["state"] == "complete", f"Incomplete: {cell['id']}"
        attempt = history[-1]
        # Recorded paths refer to EC2; relocate only the suffix under attempts/.
        relative = attempt["run_path"].split("/attempts/", 1)[1]
        run = DATA / "attempts" / relative
        info = json.loads((run / "info.json").read_text())
        summary = json.loads((run / "summary.json").read_text())
        events = [json.loads(line) for line in (run / "events.jsonl").open()]
        completed = [e for e in events if e["event"] == "completed"]
        start, end = info["warmup_seconds"], info["warmup_seconds"] + info["measurement_seconds"]
        admitted = [e for e in completed if start <= e["start_seconds"] < end]
        starts = {e["attempt_id"] for e in events if e["event"] == "started"}
        finishes = {e["attempt_id"] for e in completed}
        assert starts == finishes and len(finishes) == len(completed), cell["id"]
        success = [e for e in admitted if e["status"] == "success"]
        throughput = (
            sum(e["status"] == "success" and start <= e["finish_seconds"] < end for e in completed)
            / info["measurement_seconds"]
        )
        assert np.isclose(throughput, summary["successful_completion_throughput_qps"])
        for status, key in [
            ("success", "measurement_successes"),
            ("timeout", "measurement_timeouts"),
            ("error", "measurement_errors"),
        ]:
            assert sum(e["status"] == status for e in admitted) == summary[key]
        runtime = np.mean([e["time"] for e in success]) if success else np.nan
        assert (not success and summary["measurement_success_mean_seconds"] is None) or np.isclose(
            runtime, summary["measurement_success_mean_seconds"]
        )
        row = dict(
            cell=cell["id"],
            backend=cell["backend"],
            sf=cell["scale_factor"],
            clients=cell["workers"],
            repetition=cell["repetition"],
            throughput_qps=throughput,
            successful_runtime_s=runtime,
            admitted=len(admitted),
            successes=len(success),
            timeouts=summary["measurement_timeouts"],
            errors=summary["measurement_errors"],
        )
        row["failure_pct"] = 100 * (row["timeouts"] + row["errors"]) / len(admitted) if admitted else np.nan
        rows.append(row)
        event_rows.extend(
            dict(backend=cell["backend"], sf=cell["scale_factor"],
                 clients=cell["workers"], repetition=cell["repetition"],
                 query=e["name"], status=e["status"], duration_s=e["time"])
            for e in admitted
        )
    runs = pd.DataFrame(rows)
    query_events = pd.DataFrame(event_rows)
    assert len(runs) == 108, "This notebook expects the complete 108-cell paper matrix."
    assert runs.groupby(["backend", "sf", "clients"]).size().eq(3).all()
    return runs, query_events


def stacked_series(values):
    """Return heights and cumulative baselines for each ordered bar series."""
    result = {}
    bottom = np.zeros(len(next(iter(values.values()))))
    for label, heights in values.items():
        heights = np.asarray(heights)
        result[label] = (heights, bottom.copy())
        bottom += heights
    return result


def prepare_charts(data, scales, clients, backends):
    """Prepare plotting arrays, repetition summaries, and box-plot statistics."""
    runs, events = load_matrix(data)
    lines, outcomes, heatmaps, boxes, counts = {}, {}, {}, {}, {}
    outcome_columns = {"Success": "successes", "Failure": "errors", "Timeout": "timeouts"}
    percentages = runs[["backend", "sf", "clients"]].copy()
    for label, column in outcome_columns.items():
        percentages[label] = 100 * runs[column] / runs.admitted
    np.testing.assert_allclose(percentages[list(outcome_columns)].sum(axis=1), 100)
    means = percentages.groupby(["backend", "sf", "clients"])[list(outcome_columns)].mean()
    for backend in backends:
        backend_runs = runs[runs.backend == backend]
        heatmaps[backend] = backend_runs.pivot_table(
            index="sf", columns="clients", values="failure_pct", aggfunc="mean"
        ).reindex(index=scales, columns=clients).to_numpy()
        for sf in scales:
            selected = backend_runs[backend_runs.sf == sf]
            for metric in ("throughput_qps", "successful_runtime_s"):
                summary = selected.groupby("clients")[metric].agg(["mean", "min", "max"])
                lines[backend, sf, metric] = dict(
                    x=summary.index.to_numpy(), mean=summary["mean"].to_numpy(),
                    low=summary["min"].to_numpy(), high=summary["max"].to_numpy(),
                    point_x=selected.clients.to_numpy(), point_y=selected[metric].to_numpy(),
                )
            values = means.loc[backend, sf].reindex(clients)
            outcomes[backend, sf] = stacked_series({label: values[label].to_numpy() for label in outcome_columns})
        for sf in [*scales, None]:
            subset = events[events.backend == backend]
            if sf is not None:
                subset = subset[subset.sf == sf]
            for q in range(1, 9):
                values = subset.loc[(subset.status == "success") & (subset["query"] == f"Query {q}"), "duration_s"].to_numpy()
                assert np.all(values > 0)
                boxes[backend, sf, q] = boxplot_stats(values, whis=(5, 95)) if len(values) else None
            grouped = subset.groupby(["status", "query"]).size()
            counts[backend, sf] = stacked_series({
                status: np.array([grouped.get((status, f"Query {q}"), 0) for q in range(1, 9)])
                for status in ("success", "error", "timeout")
            })
    return dict(lines=lines, outcomes=outcomes, heatmaps=heatmaps, boxes=boxes, counts=counts)
