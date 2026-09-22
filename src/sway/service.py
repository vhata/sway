"""Application orchestration: validated decisions, independent bots, atomic saves."""

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


def _snapshot(state: GameState, bots: tuple[BotState, ...]) -> str:
    return json.dumps(
        {"schema": 1, "engine": state_to_json(state), "bots": [asdict(bot) for bot in bots]},
        sort_keys=True,
        separators=(",", ":"),
    )


def _record(saved: StoredGame) -> GameRecord:
    try:
        payload = _object(cast(object, json.loads(saved.snapshot)))
        if payload.get("schema") != 1:
            raise SaveFormatError("Unsupported game save version; the original save is preserved.")
        state = state_from_json(_text(payload.get("engine")))
        raw_bots = payload.get("bots")
        if not isinstance(raw_bots, list):
            raise SaveFormatError("Missing opponent profiles.")
        bots: list[BotState] = []
        for raw in cast(list[object], raw_bots):
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
        if state.revision != saved.revision or len(bots) != len(state.players) - 1:
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
        theme_id: str = "neutral",
    ) -> GameRecord:
        self._check_theme(theme_id)
        if len(strategies) != config.player_count - 1:
            raise ValueError("Choose one strategy for each opponent.")
        if any(profile not in STRATEGIES for profile in strategies):
            raise ValueError("Unknown opponent strategy.")
        state = new_game(config, seed)
        bots = tuple(
            BotState(profile, seed ^ ((index + 1) * 0x9E3779B97F4A7C15))
            for index, profile in enumerate(strategies)
        )
        return _record(
            self.store.create(
                uuid4().hex,
                _snapshot(state, bots),
                json.dumps(
                    {"players": [player.name for player in state.players], "strategies": strategies}
                ),
                theme_id,
            )
        )

    def load(self, game_id: str) -> GameRecord:
        return _record(self.store.load(game_id))

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
        if player != 0:
            raise ValueError("Only the human seat is available through the browser service.")
        return view_for(self.load(game_id).state, player)

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
            _snapshot(result.state, bots),
            json.dumps(asdict(command), sort_keys=True),
            json.dumps([asdict(event) for event in result.events], sort_keys=True),
            "finished" if result.state.phase == "finished" else "active",
        )
        return _record(saved)

    def submit(self, game_id: str, command: Command) -> GameRecord:
        record = self.load(game_id)
        if record.revision != command.expected_revision:
            raise StorageConflict("The game advanced. Reload before making your choice.")
        if record.state.pending is None or record.state.pending.player != 0:
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
            if decision is None or decision.player == 0 or record.state.phase == "finished":
                break
            index = decision.player - 1
            choice = choose(view_for(record.state, decision.player), decision, record.bots[index])
            bots = list(record.bots)
            bots[index] = choice.state
            record = self._apply(record, choice.command, tuple(bots))
        return record

    def set_theme(self, game_id: str, theme_id: str) -> GameRecord:
        self._check_theme(theme_id)
        return _record(self.store.set_theme(game_id, theme_id))
