"""Own the real local workerd process, persistence directory and contract requests."""

from __future__ import annotations

import json
import os
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import cast
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.environ.get("SWAY_CLOUDFLARE_TEST_PORT", "8798"))


def request(path: str) -> dict[str, object]:
    with urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=20) as response:
        return cast(dict[str, object], json.load(response))


def eventually(check: Callable[[], bool], seconds: float = 60) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except (URLError, TimeoutError):
            pass
        time.sleep(0.1)
    raise AssertionError("Local Cloudflare contract did not become ready before its deadline")


@contextmanager
def server(directory: Path, *, application: bool = False) -> Generator[None]:
    nonce = uuid4().hex
    port = PORT + 2 if application else PORT
    # Fail before launching if another process owns this port. Contract readiness
    # also checks a nonce so it can never accept a previous test worker.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
    arguments = [
        "uv",
        "run",
        "--locked",
        "pywrangler",
        "dev",
        "--config",
        "wrangler.jsonc" if application else "wrangler.test.jsonc",
        "--local",
        "--port",
        str(port),
        "--persist-to",
        str(directory / "state"),
    ]
    if application:
        arguments += [
            "--local-protocol",
            "https",
            "--var",
            f"SWAY_HOSTED_ORIGIN:https://localhost:{port}",
            "--var",
            "SWAY_HOSTED_CREDENTIALS_PER_MINUTE:1000",
            "--var",
            "SWAY_HOSTED_MUTATIONS_PER_MINUTE:1000",
        ]
    else:
        arguments += ["--var", f"CONTRACT_RUN:{nonce}"]

    def ready() -> bool:
        if process.poll() is not None:
            raise RuntimeError("Local Workers process exited before readiness")
        if not application:
            return request("/health").get("run") == nonce
        # Only the loopback test server uses a self-signed certificate.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        with urlopen(f"https://localhost:{port}/", context=context, timeout=20) as response:
            return response.status == 200

    with (directory / "workerd.log").open("a") as log:
        process = subprocess.Popen(
            arguments,
            cwd=ROOT / "deployment/cloudflare",
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            eventually(ready)
            yield
        except BaseException:
            # The test worker holds only synthetic credentials. Preserve diagnostics
            # for failures without copying production state or deployment secrets.
            print((directory / "workerd.log").read_text())
            raise
        finally:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="sway-cloudflare-contract-") as temporary:
        directory = Path(temporary)
        with server(directory):
            result = request("/")
            checks = result.get("checks")
            assert isinstance(checks, list) and len(cast(list[object], checks)) == 11, result
            print("Workers:", ", ".join(cast(list[str], checks)))
            eventually(lambda: request("/alarm").get("fired") is True)
            assert request("/bot/start").get("pending") is True
            # Stop with bot work and its future alarm still pending.
        with server(directory):
            assert request("/alarm").get("fired") is True
            # Alarm resumes the bot after restart; polling is strictly read-only.
            eventually(lambda: request("/bot/status").get("progressed") is True)
        print(
            "Workers: alarm delivery, background bot progress, persisted state after restart passed"
        )
        if "--browser" in sys.argv[1:]:
            app_directory = directory / "application"
            app_directory.mkdir()
            with server(app_directory, application=True):
                environment = dict(os.environ)
                environment["SWAY_E2E_HOSTED_URL"] = f"https://localhost:{PORT + 2}"
                subprocess.run(
                    ["scripts/e2e.sh", "-k", "independent_players"],
                    cwd=ROOT,
                    env=environment,
                    check=True,
                )


if __name__ == "__main__":
    main()
