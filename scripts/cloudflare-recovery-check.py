"""Own a private local recovery Worker and retain logs without publishing checkpoints."""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import tempfile
import time
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from pathlib import Path
from types import FrameType
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def interrupted(signum: int, frame: FrameType | None) -> None:
    del frame
    raise KeyboardInterrupt(f"Interrupted by signal {signum}")


@contextmanager
def process(
    command: Sequence[str], log: Path, environment: dict[str, str]
) -> Generator[subprocess.Popen[bytes]]:
    """Terminate the entire owned process group on success, failure or timeout."""
    with log.open("ab") as output:
        child = subprocess.Popen(
            command,
            cwd=ROOT,
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            yield child
        finally:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            # A parent may exit while one of its descendants keeps running.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=10)


def available_port(port: int) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def wait_ready(child: subprocess.Popen[bytes], port: int, timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError("Local recovery Worker exited before readiness")
        try:
            # Wrangler opens its TCP listener before registering the Worker.
            # An HTTP response requires the proxy to finish loading the runtime.
            # This RPC-only Worker has no fetch handler, so HTTP errors are expected.
            with urlopen(f"http://127.0.0.1:{port}/", timeout=1):
                return
        except HTTPError:
            return
        except (OSError, URLError):
            time.sleep(0.1)
    raise TimeoutError("Local recovery Worker did not become ready before its deadline")


def run(command: Sequence[str], log: Path, environment: dict[str, str], timeout: int) -> None:
    with process(command, log, environment) as child:
        result = child.wait(timeout=timeout)
        if result:
            raise subprocess.CalledProcessError(result, command)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8811)
    parser.add_argument("--output", type=Path, default=ROOT / "daily-evidence/recovery")
    arguments = parser.parse_args()
    port = cast(int, arguments.port)
    if not 1 <= port <= 65535:
        parser.error("--port must be between 1 and 65535")
    available_port(port)
    destination = cast(Path, arguments.output).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    evidence = Path(tempfile.mkdtemp(prefix="run-", dir=destination))
    print(f"Local recovery evidence: {evidence}", flush=True)
    environment = dict(os.environ)
    environment["SWAY_RECOVERY_WORKER"] = f"sway-recovery-ci-{uuid4().hex}"
    environment.pop("CLOUDFLARE_ACCOUNT_ID", None)
    environment.pop("SWAY_RECOVERY_OPERATOR_RUN_ID", None)
    stage = ROOT / ".cache/cloudflare-recovery"
    try:
        run(
            ["scripts/cloudflare-recovery.sh", "prepare"],
            evidence / "prepare.log",
            environment,
            600,
        )
        # Keep local databases and credential checkpoints outside uploaded evidence.
        with tempfile.TemporaryDirectory(prefix="sway-recovery-state-") as persistence:
            command = [
                "node",
                str(ROOT / "deployment/cloudflare/node_modules/wrangler/bin/wrangler.js"),
                "dev",
                "--config",
                str(stage / "wrangler.jsonc"),
                "--local",
                "--ip",
                "127.0.0.1",
                "--port",
                str(port),
                "--persist-to",
                persistence,
            ]
            with process(command, evidence / "workerd.log", environment) as worker:
                wait_ready(worker, port)
                run(
                    ["scripts/cloudflare-recovery.sh", "run-local"],
                    evidence / "controller.log",
                    environment,
                    180,
                )
        (evidence / "result.txt").write_text("passed; local RPC only, PITR not attempted\n")
    except BaseException:
        (evidence / "result.txt").write_text("failed; see retained logs\n")
        for log in sorted(evidence.glob("*.log")):
            print(f"\n{log.name}:\n{log.read_text(errors='replace')}", flush=True)
        raise
    print("Local recovery RPC checks passed; PITR not attempted.", flush=True)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupted)
    main()
