"""Enforce the engine's branch threshold separately from combined coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
from typing import cast


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Coverage report must contain JSON objects.")
    return cast(dict[str, object], value)


def _count(summary: dict[str, object], key: str) -> int:
    value = summary.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"Coverage report has an invalid {key} count.")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report_path = cast(Path, args.report)
    try:
        report = _object(cast(object, json.loads(report_path.read_text())))
        if _object(report.get("meta")).get("branch_coverage") is not True:
            raise ValueError("Engine coverage must be collected with branches enabled.")
        covered_lines = statements = covered_branches = branches = 0
        for filename, raw in _object(report.get("files")).items():
            parts = PurePosixPath(filename.replace("\\", "/")).parts
            if not any(
                left == "sway" and right == "engine"
                for left, right in zip(parts, parts[1:], strict=False)
            ):
                continue
            summary = _object(_object(raw).get("summary"))
            covered_lines += _count(summary, "covered_lines")
            statements += _count(summary, "num_statements")
            covered_branches += _count(summary, "covered_branches")
            branches += _count(summary, "num_branches")
        if not statements or not branches:
            raise ValueError("Engine statement and branch counts must both be positive.")
        if covered_lines > statements or covered_branches > branches:
            raise ValueError("Covered counts cannot exceed their totals.")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Invalid engine coverage report: {exc}\n")
    print(
        f"Engine statements: {100 * covered_lines / statements:.2f}% ({covered_lines}/{statements})"
    )
    print(
        f"Engine branches: {100 * covered_branches / branches:.2f}% ({covered_branches}/{branches}); required 90.00%"
    )
    if covered_branches * 100 < branches * 90:
        print("Engine branch coverage is below the required 90%.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
