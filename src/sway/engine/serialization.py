"""Versioned JSON snapshots. No executable objects or pickle are accepted."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import cast

from sway.engine.catalog import CATALOG
from sway.engine.core import all_cards
from sway.engine.models import (
    Card,
    Decision,
    DecisionKind,
    Effect,
    Event,
    GameConfig,
    GameState,
    Option,
    Phase,
    Player,
)

type Json = None | bool | int | float | str | list[Json] | dict[str, Json]
SNAPSHOT_VERSION = 1


class InvalidSnapshot(ValueError):
    """A save is incompatible or malformed; its original data must be preserved."""


def state_to_json(state: GameState) -> str:
    return json.dumps(
        {"version": SNAPSHOT_VERSION, "state": asdict(state)}, sort_keys=True, separators=(",", ":")
    )


def _object(value: Json) -> dict[str, Json]:
    if not isinstance(value, dict):
        raise InvalidSnapshot("Expected a JSON object")
    return value


def _list(value: Json) -> list[Json]:
    if not isinstance(value, list):
        raise InvalidSnapshot("Expected a JSON array")
    return value


def _str(value: Json) -> str:
    if not isinstance(value, str):
        raise InvalidSnapshot("Expected text")
    return value


def _int(value: Json) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise InvalidSnapshot("Expected an integer")
    return value


def _bool(value: Json) -> bool:
    if not isinstance(value, bool):
        raise InvalidSnapshot("Expected a boolean")
    return value


def _strings(value: Json) -> tuple[str, ...]:
    return tuple(_str(item) for item in _list(value))


def _cards(value: Json) -> list[Card]:
    result: list[Card] = []
    for item in _list(value):
        data = _object(item)
        definition = _str(data["definition"])
        if definition not in CATALOG:
            raise InvalidSnapshot("Unknown card definition")
        result.append(Card(_str(data["id"]), definition))
    return result


def _effect(value: Json) -> Effect:
    data = _object(value)
    return Effect(
        _str(data["kind"]),
        _int(data["player"]),
        _int(data["amount"]),
        _str(data["card_id"]),
        _str(data["instance_id"]),
        _int(data["target"]),
        _strings(data["selected"]),
    )


def _decision(value: Json) -> Decision:
    data = _object(value)
    kind = _str(data["kind"])
    if kind not in {"select", "supply", "yes_no", "order", "menu"}:
        raise InvalidSnapshot("Unknown decision kind")
    options: list[Option] = []
    for item in _list(data["options"]):
        option = _object(item)
        options.append(
            Option(
                _str(option["id"]),
                None if option["card_id"] is None else _str(option["card_id"]),
                None if option["instance_id"] is None else _str(option["instance_id"]),
            )
        )
    return Decision(
        _str(data["id"]),
        _int(data["player"]),
        cast(DecisionKind, kind),
        _str(data["prompt"]),
        tuple(options),
        _int(data["minimum"]),
        _int(data["maximum"]),
        _bool(data["ordered"]),
    )


def _player(value: Json) -> Player:
    data = _object(value)
    return Player(
        _str(data["name"]),
        _cards(data["deck"]),
        _cards(data["hand"]),
        _cards(data["discard"]),
        _cards(data["in_play"]),
        _cards(data["revealed"]),
        _cards(data["looked"]),
        _cards(data["set_aside"]),
        _int(data["turns"]),
    )


def _event(value: Json) -> Event:
    data = _object(value)
    return Event(
        _str(data["kind"]),
        _int(data["player"]),
        tuple(_cards(data["cards"])),
        _int(data["amount"]),
        None if data["audience"] is None else _int(data["audience"]),
    )


def _decode(data: dict[str, Json]) -> GameState:
    config = _object(data["config"])
    phase = _str(data["phase"])
    if phase not in {"action", "buy", "finished"}:
        raise InvalidSnapshot("Unknown turn phase")
    return GameState(
        config=GameConfig(
            _int(config["player_count"]),
            _strings(config["kingdom"]),
            _strings(config["player_names"]),
        ),
        seed=_int(data["seed"]),
        rng_state=_int(data["rng_state"]),
        players=[_player(item) for item in _list(data["players"])],
        supply={key: _int(value) for key, value in _object(data["supply"]).items()},
        trash=_cards(data["trash"]),
        active_player=_int(data["active_player"]),
        phase=cast(Phase, phase),
        actions=_int(data["actions"]),
        buys=_int(data["buys"]),
        coins=_int(data["coins"]),
        revision=_int(data["revision"]),
        turn=_int(data["turn"]),
        pending=None if data["pending"] is None else _decision(data["pending"]),
        pending_effect=None if data["pending_effect"] is None else _effect(data["pending_effect"]),
        effects=[_effect(item) for item in _list(data["effects"])],
        events=[_event(item) for item in _list(data["events"])],
        next_instance_id=_int(data["next_instance_id"]),
        next_decision_id=_int(data["next_decision_id"]),
        merchant_bonus=_int(data["merchant_bonus"]),
        silver_played=_bool(data["silver_played"]),
        buying_started=_bool(data["buying_started"]),
        scores=tuple(_int(item) for item in _list(data["scores"])),
        winners=tuple(_int(item) for item in _list(data["winners"])),
    )


def _validate(state: GameState) -> None:
    count = len(state.players)
    if (
        not 2 <= count <= 4
        or state.config.player_count != count
        or not 0 <= state.active_player < count
    ):
        raise InvalidSnapshot("Invalid players")
    if any(key not in CATALOG or value < 0 for key, value in state.supply.items()):
        raise InvalidSnapshot("Invalid supply")
    if (
        "victory3" not in state.supply
        or min(state.actions, state.buys, state.coins, state.revision) < 0
    ):
        raise InvalidSnapshot("Invalid turn state")
    cards = state.trash + [card for player in state.players for card in all_cards(player)]
    if len({card.id for card in cards}) != len(cards):
        raise InvalidSnapshot("A card occurs in more than one zone")
    if (state.pending is None) != (state.pending_effect is None):
        raise InvalidSnapshot("Decision and continuation disagree")
    if state.pending is not None:
        pending = state.pending
        if not 0 <= pending.player < count or not 0 <= pending.minimum <= pending.maximum <= len(
            pending.options
        ):
            raise InvalidSnapshot("Invalid decision bounds")
        if len({option.id for option in pending.options}) != len(pending.options):
            raise InvalidSnapshot("Duplicate decision option")
    if state.phase == "finished" and (state.pending is not None or state.effects):
        raise InvalidSnapshot("Finished game has unresolved decisions")


def state_from_json(snapshot: str) -> GameState:
    """Restore a snapshot or raise InvalidSnapshot without modifying its source."""
    try:
        envelope = _object(cast(Json, json.loads(snapshot)))
        if _int(envelope["version"]) != SNAPSHOT_VERSION:
            raise InvalidSnapshot("Unsupported save version; original save is unchanged")
        state = _decode(_object(envelope["state"]))
        _validate(state)
        return state
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise InvalidSnapshot("Malformed save; original save is unchanged") from exc
