"""Bounded, reproducible bot matches: ``python -m sway.simulate --help``."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from random import Random
from typing import cast

from sway.bots import STRATEGIES, BotState, choose
from sway.engine import KINGDOM_IDS, GameConfig, advance, new_game, view_for


@dataclass(frozen=True)
class SimulationResult:
    seed: int
    players: int
    profiles: tuple[str, ...]
    kingdom: tuple[str, ...]
    finished: bool
    decisions: int
    turns: int
    scores: tuple[int, ...]
    winners: tuple[int, ...]


def simulate_game(
    config: GameConfig,
    seed: int,
    profiles: tuple[str, ...],
    max_decisions: int = 4000,
) -> SimulationResult:
    """Play all seats through filtered decisions; never force a game to end."""
    if len(profiles) != config.player_count or any(
        profile not in STRATEGIES for profile in profiles
    ):
        raise ValueError("Choose a supported profile for every simulated seat.")
    if max_decisions < 1:
        raise ValueError("The decision budget must be positive.")
    state = new_game(config, seed)
    bots = [
        BotState(profile, seed ^ ((seat + 1) * 0xD1B54A32D192ED03))
        for seat, profile in enumerate(profiles)
    ]
    count = 0
    while state.phase != "finished" and count < max_decisions:
        decision = state.pending
        if decision is None:
            raise RuntimeError("An unfinished game has no pending decision.")
        player = decision.player
        choice = choose(view_for(state, player), decision, bots[player])
        state = advance(state, choice.command).state
        bots[player] = choice.state
        count += 1
    return SimulationResult(
        seed,
        config.player_count,
        profiles,
        config.kingdom,
        state.phase == "finished",
        count,
        state.turn,
        state.scores,
        state.winners,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--players", type=int, choices=(2, 3, 4), default=2)
    parser.add_argument("--max-decisions", type=int, default=4000)
    parser.add_argument("--profiles", nargs="+", choices=STRATEGIES, default=list(STRATEGIES))
    parser.add_argument(
        "--kingdom", default="preset", help="preset, random, or ten comma-separated stable card IDs"
    )
    arguments = parser.parse_args(argv)
    seed = cast(int, arguments.seed)
    games = cast(int, arguments.games)
    players = cast(int, arguments.players)
    max_decisions = cast(int, arguments.max_decisions)
    requested = cast(list[str], arguments.profiles)
    kingdom_arg = cast(str, arguments.kingdom)
    if games < 1 or max_decisions < 1:
        parser.error("--games and --max-decisions must be positive")
    profiles = tuple(requested[seat % len(requested)] for seat in range(players))
    outcomes: list[SimulationResult] = []
    for offset in range(games):
        game_seed = seed + offset
        if kingdom_arg == "random":
            kingdom = tuple(sorted(Random(game_seed ^ 0x94D049BB133111EB).sample(KINGDOM_IDS, 10)))
        elif kingdom_arg == "preset":
            kingdom = GameConfig().kingdom
        else:
            kingdom = tuple(item.strip() for item in kingdom_arg.split(","))
        try:
            outcomes.append(
                simulate_game(GameConfig(players, kingdom), game_seed, profiles, max_decisions)
            )
        except ValueError as exc:
            parser.error(str(exc))
    unfinished = sum(not outcome.finished for outcome in outcomes)
    print(
        json.dumps(
            {
                "games": [asdict(outcome) for outcome in outcomes],
                "completed": len(outcomes) - unfinished,
                "unfinished": unfinished,
            },
            sort_keys=True,
        )
    )
    return 1 if unfinished else 0


if __name__ == "__main__":
    raise SystemExit(main())
