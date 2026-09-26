"""Run the exact Workers domain contract against the self-hosted SQLite adapter."""

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import cast

from sway.hosting.state import StateStore
from sway.hosting.storage import HostedStore


def test_shared_cloudflare_contract(tmp_path: Path) -> None:
    namespace = runpy.run_path(
        str(Path(__file__).parents[1] / "deployment/cloudflare/contract_checks.py")
    )
    check = cast(Callable[[StateStore], list[str]], namespace["run"])
    assert len(check(HostedStore(tmp_path / "hosted.sqlite3"))) == 9
