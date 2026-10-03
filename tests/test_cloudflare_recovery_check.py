"""The daily recovery runner must stop failed workers and refuse occupied ports."""

import os
import runpy
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

RUNNER: dict[str, Any] = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts/cloudflare-recovery-check.py")
)


def test_recovery_check_rejects_an_occupied_port() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with pytest.raises(OSError):
            RUNNER["available_port"](listener.getsockname()[1])


def test_recovery_check_preserves_failure_and_reaps_child(tmp_path: Path) -> None:
    log = tmp_path / "worker.log"
    with pytest.raises(RuntimeError, match="exited before readiness"):
        with RUNNER["process"](
            [sys.executable, "-c", "print('worker failed', flush=True); raise SystemExit(7)"],
            log,
            dict(os.environ),
        ) as child:
            assert child.wait(timeout=10) == 7
            RUNNER["wait_ready"](child, 1, timeout=1)
    assert "worker failed" in log.read_text()


def test_recovery_check_timeout_reaps_running_child(tmp_path: Path) -> None:
    with RUNNER["process"](
        [sys.executable, "-c", "import time; time.sleep(60)"],
        tmp_path / "worker.log",
        dict(os.environ),
    ) as child:
        with pytest.raises(subprocess.TimeoutExpired):
            child.wait(timeout=0.01)
    assert child.poll() is not None
