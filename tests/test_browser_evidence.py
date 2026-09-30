"""Browser reruns must preserve failed evidence and propagate pytest failures."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def test_browser_reruns_preserve_failure_evidence(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("e2e.sh", "_common.sh"):
        shutil.copy2(root / "scripts" / name, scripts / name)
    (tmp_path / "src/sway").mkdir(parents=True)
    (tmp_path / "src/sway/web.py").touch()
    binaries = tmp_path / "bin"
    binaries.mkdir()
    # Model pytest-playwright's destructive output initialization without browsers.
    uv = binaries / "uv"
    uv.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output) output="$2"; shift ;;
    --basetemp) runtime="$2"; shift ;;
  esac
  shift
done
rm -rf "$output" "$runtime"
mkdir -p "$output" "$runtime" "$SWAY_E2E_ARTIFACT_DIR"
printf 'trace evidence' > "$output/trace.zip"
printf 'hosted evidence' > "$SWAY_E2E_ARTIFACT_DIR/hosted.zip"
printf 'server evidence' > "$runtime/server.log"
echo "test output, status=$SWAY_TEST_EXIT_STATUS"
exit "$SWAY_TEST_EXIT_STATUS"
"""
    )
    uv.chmod(0o755)
    git = binaries / "git"
    git.write_text("#!/usr/bin/env bash\nprintf 'reviewed-commit\\n'\n")
    git.chmod(0o755)
    environment = {**os.environ, "PATH": f"{binaries}:{os.environ['PATH']}"}
    # An old default-output trace must survive the very first upgraded run too.
    legacy = tmp_path / "test-results" / "legacy.zip"
    legacy.parent.mkdir()
    legacy.write_text("legacy evidence")
    snapshots: dict[Path, bytes] = {}
    for expected_status in (1, 0):
        result = subprocess.run(
            [
                str(scripts / "e2e.sh"),
                "-k",
                "complete_game or hosted",
                "--output",
                str(legacy.parent),
                "--basetemp",
                str(tmp_path / "browser-evidence"),
            ],
            cwd=tmp_path,
            env={**environment, "SWAY_TEST_EXIT_STATUS": str(expected_status)},
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == expected_status, result.stderr
        printed_path = result.stdout.splitlines()[0].removeprefix("Browser evidence: ")
        run = Path(printed_path)
        assert run.parent == tmp_path / "browser-evidence"
        assert (run / "exit-status.txt").read_text() == f"{expected_status}\n"
        assert (run / "commit.txt").read_text() == "reviewed-commit\n"
        assert "complete_game" in (run / "arguments.txt").read_text()
        assert f"status={expected_status}" in (run / "pytest.log").read_text()
        assert (run / "playwright/trace.zip").read_text() == "trace evidence"
        assert (run / "hosted/hosted.zip").read_text() == "hosted evidence"
        assert (run / "runtime/server.log").read_text() == "server evidence"
        for path, content in snapshots.items():
            assert path.read_bytes() == content
        snapshots.update({path: path.read_bytes() for path in run.rglob("*") if path.is_file()})
    assert legacy.read_text() == "legacy evidence"
    # An ordinary pytest session still clears its default output; retained browser
    # runs must be outside it, including their temporary databases and logs.
    shutil.rmtree(legacy.parent)
    for path, content in snapshots.items():
        assert path.read_bytes() == content
    assert len(list((tmp_path / "browser-evidence").glob("run-*"))) == 2
