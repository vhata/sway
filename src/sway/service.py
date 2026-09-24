"""Game orchestration with explicit human controllers and independent bot state.

The caller supplies a trusted human seat. HTTP clients must not select that seat;
authentication and membership belong to a future application boundary.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import cast
from uuid import uuid4

from sway.bots import STRATEGIES, BotState, choose
from sway.engine import (
    Command,
    GameConfig,
    GameState,
    InvalidCommand,
    PlayerView,
    advance,
    new_game,
    state_from_json,
    state_to_json,
    view_for,
)
from sway.storage import SaveFormatError, StorageConflict, Store, StoredGame


@dataclass(frozen=True)
class GameSummary:
    game_id: str
    revision: int
    theme_id: str
    status: str
    updated_at: str
    player_names: tuple[str, ...]
    strategies: tuple[str, ...]


@dataclass(frozen=True)
class GameRecord:
    game_id: str
    revision: int
    theme_id: str
    status: str
    updated_at: str
    player_names: tuple[str, ...]
    strategies: tuple[str, ...]
    state: GameState
    bots: tuple[BotState, ...]
    human_seats: frozenset[int]

    @property
    def bot_seats(self) -> tuple[int, ...]:
        """The seat for each entry in bots, in ascending player order."""
        return _bot_seats(len(self.state.players), self.human_seats)


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SaveFormatError("Expected a save object.")
    return cast(dict[str, object], value)


def _integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise SaveFormatError("Expected a save integer.")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise SaveFormatError("Expected save text.")
    return value


def _human_seats(value: object, player_count: int) -> frozenset[int]:
    if not isinstance(value, frozenset) or not value:
        raise ValueError("Choose at least one human seat as a frozenset of player indices.")
    seats = cast(frozenset[object], value)
    if any(
        not isinstance(seat, int) or isinstance(seat, bool) or not 0 <= seat < player_count
        for seat in seats
    ):
        raise ValueError("Human seats must be integer player indices within the game.")
    return cast(frozenset[int], value)


def _bot_seats(player_count: int, human_seats: frozenset[int]) -> tuple[int, ...]:
    return tuple(player for player in range(player_count) if player not in human_seats)


def serialize_game(
    state: GameState, bots: tuple[BotState, ...], human_seats: frozenset[int]
) -> str:
    """Encode an internal application snapshot shared by local and hosted stores."""
    return json.dumps(
        {
            "schema": 2,
            "engine": state_to_json(state),
            "human_seats": sorted(human_seats),
            "bots": {
                str(player): asdict(bot)
                for player, bot in zip(
                    _bot_seats(len(state.players), human_seats), bots, strict=True
                )
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def deserialize_game(saved: StoredGame) -> GameRecord:
    """Validate an internal snapshot without exposing it to presentation code."""
    try:
        payload = _object(cast(object, json.loads(saved.snapshot)))
        schema = _integer(payload.get("schema"))
        if schema not in {1, 2}:
            raise SaveFormatError("Unsupported game save version; the original save is preserved.")
        state = state_from_json(_text(payload.get("engine")))
        if schema == 1:
            # Original local saves always used human seat 0 and positional bots.
            human_seats = frozenset({0})
            raw_bots = payload.get("bots")
            if not isinstance(raw_bots, list):
                raise SaveFormatError("Missing opponent profiles.")
            bot_values = cast(list[object], raw_bots)
        else:
            raw_humans = payload.get("human_seats")
            if not isinstance(raw_humans, list):
                raise SaveFormatError("Missing human seat assignments.")
            indices = tuple(_integer(value) for value in cast(list[object], raw_humans))
            if len(set(indices)) != len(indices):
                raise SaveFormatError("A human seat is assigned more than once.")
            human_seats = _human_seats(frozenset(indices), len(state.players))
            by_seat = _object(payload.get("bots"))
            bot_seats = _bot_seats(len(state.players), human_seats)
            if set(by_seat) != {str(player) for player in bot_seats}:
                raise SaveFormatError("Bot assignments do not match the game's remaining seats.")
            bot_values = [by_seat[str(player)] for player in bot_seats]
        bots: list[BotState] = []
        for raw in bot_values:
            item = _object(raw)
            bot = BotState(
                profile=_text(item.get("profile")),
                seed=_integer(item.get("seed")),
                decisions=_integer(item.get("decisions")),
                version=_integer(item.get("version")),
            )
            if bot.profile not in STRATEGIES or bot.version != 1 or bot.decisions < 0:
                raise SaveFormatError("Unsupported opponent strategy version.")
            bots.append(bot)
        if state.revision != saved.revision or len(bots) != len(state.players) - len(human_seats):
            raise SaveFormatError("The game save has inconsistent state or opponents.")
        return GameRecord(
            game_id=saved.game_id,
            revision=saved.revision,
            theme_id=saved.theme_id,
            status=saved.status,
            updated_at=saved.updated_at,
            player_names=tuple(player.name for player in state.players),
            strategies=tuple(bot.profile for bot in bots),
            state=state,
            bots=tuple(bots),
            human_seats=human_seats,
        )
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise SaveFormatError(
            "The saved game is invalid or incompatible; it was not changed."
        ) from exc


class GameService:
    def __init__(self, store: Store) -> None:
        self.store = store

    @staticmethod
    def _check_theme(theme_id: str) -> None:
        if re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", theme_id) is None:
            raise ValueError("Invalid theme identifier.")

    def create(
        self,
        config: GameConfig,
        seed: int,
        strategies: tuple[str, ...],
        theme_id: str = "common-ground",
        *,
        human_seats: frozenset[int] = frozenset({0}),
    ) -> GameRecord:
        self._check_theme(theme_id)
        human_seats = _human_seats(human_seats, config.player_count)
        bot_seats = _bot_seats(config.player_count, human_seats)
        if len(strategies) != len(bot_seats):
            raise ValueError("Choose one strategy for each opponent.")
        if any(profile not in STRATEGIES for profile in strategies):
            raise ValueError("Unknown opponent strategy.")
        state = new_game(config, seed)
        bots = tuple(
            BotState(profile, seed ^ (player * 0x9E3779B97F4A7C15))
            for player, profile in zip(bot_seats, strategies, strict=True)
        )
        return deserialize_game(
            self.store.create(
                uuid4().hex,
                serialize_game(state, bots, human_seats),
                json.dumps(
                    {
                        "players": [player.name for player in state.players],
                        "strategies": strategies,
                        "human_seats": sorted(human_seats),
                    }
                ),
                theme_id,
            )
        )

    def load(self, game_id: str) -> GameRecord:
        return deserialize_game(self.store.load(game_id))

    def list_games(self) -> list[GameSummary]:
        summaries: list[GameSummary] = []
        for saved in self.store.list_games():
            # Listing must not deserialize the engine: one old or damaged save
            # must not prevent users from opening their other games.
            names: tuple[str, ...] = ()
            strategies: tuple[str, ...] = ()
            try:
                metadata = _object(cast(object, json.loads(saved.metadata)))
                raw_names, raw_strategies = metadata.get("players"), metadata.get("strategies")
                if isinstance(raw_names, list):
                    names = tuple(_text(value) for value in cast(list[object], raw_names))
                if isinstance(raw_strategies, list):
                    strategies = tuple(_text(value) for value in cast(list[object], raw_strategies))
            except (ValueError, SaveFormatError):
                names = ("Saved game (metadata unavailable)",)
            summaries.append(
                GameSummary(
                    saved.game_id,
                    saved.revision,
                    saved.theme_id,
                    saved.status,
                    saved.updated_at,
                    names,
                    strategies,
                )
            )
        return summaries

    def view(self, game_id: str, player: int = 0) -> PlayerView:
        record = self.load(game_id)
        self._check_human_player(record, player)
        return view_for(record.state, player)

    @staticmethod
    def _check_human_player(record: GameRecord, player: object) -> None:
        if (
            not isinstance(player, int)
            or isinstance(player, bool)
            or player not in record.human_seats
        ):
            raise ValueError("Choose a configured human seat.")

    def _apply(
        self, record: GameRecord, command: Command, bots: tuple[BotState, ...]
    ) -> GameRecord:
        # Compute outside the storage transaction. A concurrent writer is rejected
        # by commit's expected-revision check, never overwritten.
        result = advance(record.state, command)
        saved = self.store.commit(
            record.game_id,
            command.expected_revision,
            command.decision_id,
            serialize_game(result.state, bots, record.human_seats),
            json.dumps(asdict(command), sort_keys=True),
            json.dumps([asdict(event) for event in result.events], sort_keys=True),
            "finished" if result.state.phase == "finished" else "active",
        )
        return deserialize_game(saved)

    def submit(self, game_id: str, command: Command, *, player: int = 0) -> GameRecord:
        record = self.load(game_id)
        self._check_human_player(record, player)
        if record.revision != command.expected_revision:
            raise StorageConflict("The game advanced. Reload before making your choice.")
        if record.state.pending is None or record.state.pending.player != player:
            raise InvalidCommand("It is not your decision.")
        return self._apply(record, command, record.bots)

    def advance_bots(self, game_id: str, expected_revision: int, max_steps: int = 8) -> GameRecord:
        if not 1 <= max_steps <= 32:
            raise ValueError("Bot steps must be between 1 and 32.")
        record = self.load(game_id)
        if record.revision != expected_revision:
            raise StorageConflict("The game advanced. Reload before continuing.")
        for _ in range(max_steps):
            decision = record.state.pending
            if (
                decision is None
                or decision.player in record.human_seats
                or record.state.phase == "finished"
            ):
                break
            index = record.bot_seats.index(decision.player)
            choice = choose(view_for(record.state, decision.player), decision, record.bots[index])
            bots = list(record.bots)
            bots[index] = choice.state
            record = self._apply(record, choice.command, tuple(bots))
        return record

    def set_theme(self, game_id: str, theme_id: str) -> GameRecord:
        self._check_theme(theme_id)
        return deserialize_game(self.store.set_theme(game_id, theme_id))
