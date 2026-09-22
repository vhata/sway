"""Headless results distinguish completion from exhausting a bounded run."""

from __future__ import annotations

import json
from typing import cast

import pytest

from sway.engine import GameConfig
from sway.simulate import main, simulate_game


def test_simulation_is_deterministic_and_reports_unfinished() -> None:
    config = GameConfig()
    profiles = ("economy", "attack")
    first = simulate_game(config, 72, profiles)
    assert first.finished
    assert first == simulate_game(config, 72, profiles)
    unfinished = simulate_game(config, 72, profiles, max_decisions=1)
    assert not unfinished.finished
    assert unfinished.decisions == 1
    assert unfinished.winners == ()
    assert unfinished.scores == ()


def test_cli_reports_seed_profiles_and_budget(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "--seed",
                "71",
                "--games",
                "2",
                "--players",
                "3",
                "--max-decisions",
                "1",
                "--profiles",
                "attack",
                "--kingdom",
                "random",
            ]
        )
        == 1
    )
    payload = cast(dict[str, object], json.loads(capsys.readouterr().out))
    assert payload["unfinished"] == 2
    assert payload["completed"] == 0
    games = cast(list[dict[str, object]], payload["games"])
    assert [game["seed"] for game in games] == [71, 72]
    assert games[0]["profiles"] == ["attack"] * 3
    assert games[0]["kingdom"] != games[1]["kingdom"]


@pytest.mark.parametrize("args", (["--games", "0"], ["--max-decisions", "0"], ["--kingdom", "k01"]))
def test_cli_rejects_invalid_setup(args: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2


def test_api_rejects_missing_profiles_and_nonpositive_budget() -> None:
    with pytest.raises(ValueError, match="every simulated seat"):
        simulate_game(GameConfig(), 1, ("economy",))
    with pytest.raises(ValueError, match="positive"):
        simulate_game(GameConfig(), 1, ("economy", "attack"), 0)
