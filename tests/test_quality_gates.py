"""A strong statement score must not conceal insufficient engine branches."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

GATE = Path(__file__).resolve().parents[1] / "scripts" / "check-coverage.py"


@pytest.mark.parametrize("covered,expected", ((89, 1), (90, 0)))
def test_engine_branch_threshold_is_independent(
    tmp_path: Path, covered: int, expected: int
) -> None:
    report = tmp_path / "coverage.json"
    report.write_text(
        json.dumps(
            {
                "meta": {"branch_coverage": True},
                "files": {
                    "src/sway/engine/core.py": {
                        "summary": {
                            "covered_lines": 1000,
                            "num_statements": 1000,
                            "covered_branches": covered,
                            "num_branches": 100,
                        }
                    },
                    "src/sway/web.py": {
                        "summary": {
                            "covered_lines": 0,
                            "num_statements": 10000,
                            "covered_branches": 0,
                            "num_branches": 10000,
                        }
                    },
                },
            }
        )
    )
    result = subprocess.run(
        [sys.executable, str(GATE), str(report)], capture_output=True, text=True, check=False
    )
    assert result.returncode == expected
    assert "Engine statements: 100.00% (1000/1000)" in result.stdout
    assert f"Engine branches: {covered}.00% ({covered}/100)" in result.stdout


def test_missing_branch_measurement_cannot_pass(tmp_path: Path) -> None:
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps({"meta": {"branch_coverage": False}, "files": {}}))
    result = subprocess.run(
        [sys.executable, str(GATE), str(report)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 1
    assert "branches enabled" in result.stderr
