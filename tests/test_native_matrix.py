"""Native wrapper failure propagation and child cleanup."""

import os
import sys

import pytest

from jsonbench.native_matrix import execute


def test_failed_child_stops_phase(tmp_path, monkeypatch):
    import jsonbench.native_matrix as native

    monkeypatch.setattr(native.Path, "read_text", lambda self: "")
    monkeypatch.setattr(native, "command", lambda *args: "")
    with pytest.raises(RuntimeError, match="exited 7"):
        execute([sys.executable, "-c", "raise SystemExit(7)"], tmp_path, "test", os.environ.copy())


def test_sampling_failure_terminates_child(tmp_path, monkeypatch):
    import jsonbench.native_matrix as native

    real = native.subprocess.Popen
    children = []

    def spawn(*args, **kwargs):
        child = real(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(native.subprocess, "Popen", spawn)

    def fail(*args):
        raise RuntimeError("sampling failed")

    monkeypatch.setattr(native, "command", fail)
    # Linux /proc is used on the target; substitute it for portable unit testing.
    monkeypatch.setattr(native.Path, "read_text", lambda self: "")
    with pytest.raises(RuntimeError, match="sampling failed"):
        execute(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            tmp_path,
            "test",
            os.environ.copy(),
        )
    assert children[0].poll() is not None
