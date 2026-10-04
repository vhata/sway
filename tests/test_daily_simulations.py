"""The daily corpus must retain failures even when subsequent batches succeed."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def test_failed_simulation_batch_does_not_short_circuit_or_turn_green(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("daily-simulations.sh", "_common.sh"):
        shutil.copy2(root / "scripts" / name, scripts / name)
    simulator = scripts / "simulate.sh"
    simulator.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> invocations.txt
if [[ ! -f first-failed ]]; then
  touch first-failed
  echo '{"unfinished": 1}'
  echo 'decision budget exhausted' >&2
  exit 1
fi
echo '{"unfinished": 0}'
"""
    )
    simulator.chmod(0o755)
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name in ("uv", "git"):
        binary = binaries / name
        binary.write_text("#!/usr/bin/env bash\necho tested-commit\n")
        binary.chmod(0o755)
    result = subprocess.run(
        [str(scripts / "daily-simulations.sh"), "4", "12345"],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{binaries}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    invocations = (tmp_path / "invocations.txt").read_text().splitlines()
    assert len(invocations) == 24  # Continue through every independent corpus batch.
    assert any("--seed 0" in command for command in invocations)
    assert any("--seed 12345" in command for command in invocations)
    evidence = tmp_path / "daily-evidence/simulations-4"
    assert len(list(evidence.glob("*.json"))) == 24
    assert (evidence / "fixed-preset-economy.json").read_text() == '{"unfinished": 1}\n'
    assert "decision budget exhausted" in (evidence / "fixed-preset-economy.log").read_text()
    assert (evidence / "commit.txt").read_text() == "tested-commit\n"
