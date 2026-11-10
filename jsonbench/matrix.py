"""Sequential matrix execution with immutable plans and append-only run attempts."""

import argparse
import fcntl
import hashlib
import json
import os
import socket
import subprocess
import time
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path

from jsonbench.benchmark.supervisor import run_supervised
from jsonbench.config_loader.config_loader import ConfigLoader
from jsonbench.data_generator.data_generator import generate_dataset, load_dataset, validate_dataset
from jsonbench.query_generator.query_generator import generate_queries


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2))
    temporary.replace(path)


def expand(manifest):
    for key in (
        "cooldown_seconds",
        "warmup_seconds",
        "duration",
        "query_timeout_seconds",
        "startup_timeout_seconds",
        "drain_timeout_seconds",
    ):
        value = manifest[key]
        if type(value) not in (int, float) or not 0 <= value < float("inf"):
            raise ValueError(f"Invalid {key}")
    if manifest.get("format_version") != 1:
        raise ValueError("Unsupported matrix format")
    if manifest["backends"] != ["mongodb", "couchbase"]:
        raise ValueError("Expected sequential mongodb and couchbase phases")
    for key in ("scale_factors", "workers", "repetition_seeds"):
        values = manifest[key]
        if (
            not values
            or len(set(values)) != len(values)
            or any(type(v) is not int or v < 0 for v in values)
        ):
            raise ValueError(f"Invalid {key}")
    if min(manifest["scale_factors"]) < 1 or min(manifest["workers"]) < 1:
        raise ValueError("Scales and workers must be positive")
    cells = []
    for backend in manifest["backends"]:
        for scale in manifest["scale_factors"]:
            for repetition, seed in enumerate(manifest["repetition_seeds"], 1):
                workers = manifest["workers"][:: 1 if repetition % 2 else -1]
                for clients in workers:
                    cells.append(
                        dict(
                            id=f"{backend}-s{scale}-r{repetition}-w{clients}",
                            backend=backend,
                            scale_factor=scale,
                            repetition=repetition,
                            seed=seed,
                            workers=clients,
                        )
                    )
    return cells


@contextmanager
def locked(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another matrix command holds this output directory") from exc
        yield


def plan(manifest_path, root):
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text())
    queries = (manifest_path.parent / manifest["query_template_path"]).resolve()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    content = dict(
        dependencies={name: version(name) for name in ("pymongo", "couchbase", "Faker")},
        manifest=manifest,
        query_sha256=hashlib.sha256(queries.read_bytes()).hexdigest(),
        revision=revision,
        cells=expand(manifest),
    )
    target = root / "plan.json"
    if target.exists() and json.loads(target.read_text()) != content:
        raise ValueError(
            "Plan, query templates or code revision changed; use a fresh output directory"
        )
    if not target.exists():
        atomic_json(target, content)
    return manifest, queries, content["cells"]


def dataset_path(root, scale):
    return root / "datasets" / f"s{scale}"


def prepare(manifest, root):
    for scale in manifest["scale_factors"]:
        path = dataset_path(root, scale)
        if path.exists():
            data = validate_dataset(path)
            if any(
                data[key] != value
                for key, value in {
                    "seed": manifest["dataset_seed"],
                    "scale_factor": scale,
                    "reference_date": manifest["reference_date"],
                }.items()
            ):
                raise ValueError(f"Dataset configuration mismatch: {path}")
        else:
            generate_dataset(
                path,
                scale=scale,
                seed=manifest["dataset_seed"],
                reference_date=manifest["reference_date"],
            )

    fingerprints = {
        str(scale): hashlib.sha256(
            (dataset_path(root, scale) / "manifest.json").read_bytes()
        ).hexdigest()
        for scale in manifest["scale_factors"]
    }
    snapshot = root / "dataset-checksums.json"
    if snapshot.exists() and json.loads(snapshot.read_text()) != fingerprints:
        raise ValueError("Dataset manifests changed; use a fresh output root")
    atomic_json(snapshot, fingerprints)


def ensure_other_database_stopped(backend):
    # EC2 runner intentionally supports local, sequential database phases only.
    port = 8091 if backend == "mongodb" else 27017
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            raise RuntimeError(f"Other database appears active on port {port}; stop it first")
    except ConnectionRefusedError:
        pass


def make_config(manifest, queries, root, cell, connection):
    settings = {
        k: manifest[k]
        for k in (
            "warmup_seconds",
            "duration",
            "query_timeout_seconds",
            "drain_timeout_seconds",
            "startup_timeout_seconds",
            "query_selection_probability",
        )
    }
    settings.update(
        database=cell["backend"],
        scale_factor=cell["scale_factor"],
        workers=cell["workers"],
        seed=cell["seed"],
        create_indexes=True,
        replace_collections=True,
        dataset_directory=str(dataset_path(root, cell["scale_factor"])),
        query_template_path=str(queries),
        connection=connection,
    )
    # Keep credentials out of persisted configuration.
    path = root / "current-config.json"
    atomic_json(path, {k: v for k, v in settings.items() if k != "connection"})
    config = ConfigLoader(path)
    config.settings["connection"] = connection
    return config


def completed_attempt(attempt):
    base = Path(attempt["directory"])
    candidates = list(base.glob("*/*/info.json"))
    if len(candidates) != 1:
        return False
    info = json.loads(candidates[0].read_text())
    return info.get("state") == "complete" and candidates[0].with_name("summary.json").is_file()


def run(manifest, queries, cells, root, backend, connections, retry_failed=False):
    ensure_other_database_stopped(backend)
    state_path = root / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"attempts": {}}
    # Credentials are resolved only in memory; connections are pinned by a digest.
    digest = hashlib.sha256(json.dumps(connections, sort_keys=True).encode()).hexdigest()
    if state.get("connections_sha256", digest) != digest:
        raise ValueError("Connection configuration changed")
    state["connections_sha256"] = digest
    connection = dict(connections[backend])
    if "password_env" in connection:
        connection["password"] = os.environ[connection.pop("password_env")]
    expected = manifest["versions"][backend]
    loaded_scale = None
    for cell in (c for c in cells if c["backend"] == backend):
        history = state["attempts"].setdefault(cell["id"], [])
        if history and history[-1]["state"] == "complete":
            if not completed_attempt(history[-1]):
                raise RuntimeError(f"Completed artifacts missing/corrupt: {cell['id']}")
            continue
        if history and not retry_failed:
            raise RuntimeError(
                f"Unfinished/failed cell {cell['id']}; inspect artifacts, then use --retry-failed"
            )
        # Never infer completion from an orphan process's output: explicit retries are new attempts.
        cooldown_until = state.get("cooldown_until", 0)
        while time.time() < cooldown_until:
            time.sleep(min(10, cooldown_until - time.time()))
        ensure_other_database_stopped(backend)
        config = make_config(manifest, queries, root, cell, connection)
        attempt_dir = root / "attempts" / cell["id"] / f"{len(history) + 1:03d}"
        attempt = {"state": "running", "directory": str(attempt_dir), "started_at": time.time()}
        history.append(attempt)
        atomic_json(state_path, state)
        try:
            database = config.get_database()
            observed = database.server_version()
            if observed.split("-")[0] != expected:
                raise ValueError(f"Expected {expected}, observed {observed}")
            if loaded_scale != cell["scale_factor"]:
                load_dataset(config)
                loaded_scale = cell["scale_factor"]
            native = generate_queries(config)
            config.close()
            config.settings["results_directory"] = str(attempt_dir)
            path = run_supervised(config, native)
            attempt.update(state="complete", run_path=str(path), finished_at=time.time())
        except BaseException:
            attempt.update(state="failed", finished_at=time.time())
            raise
        finally:
            config.close()
            state["cooldown_until"] = time.time() + manifest["cooldown_seconds"]
            atomic_json(state_path, state)
    print(f"{backend} phase complete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "prepare", "run"])
    parser.add_argument("--manifest", default="experiments/paper-matrix.json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--backend", choices=["mongodb", "couchbase"])
    parser.add_argument("--connections", default="experiments/connections.example.json")
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    root = Path(args.output).resolve()
    with locked(root):
        manifest, queries, cells = plan(args.manifest, root)
        print(f"{len(cells)} runs; {len(manifest['repetition_seeds'])} repetitions")
        if args.action == "prepare":
            prepare(manifest, root)
        elif args.action == "run":
            if subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=no"], text=True
            ).strip():
                raise RuntimeError("Commit tracked changes before running a matrix")
            if not args.backend:
                parser.error("run requires --backend")
            prepare(manifest, root)
            run(
                manifest,
                queries,
                cells,
                root,
                args.backend,
                json.loads(Path(args.connections).read_text()),
                args.retry_failed,
            )


if __name__ == "__main__":
    main()
