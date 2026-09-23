"""Versioned JSON snapshots. No executable objects or pickle are accepted."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import cast

from sway.engine.catalog import CATALOG, KINGDOM_IDS
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

_STACK_EFFECTS = frozenset(
    {
        "resolve",
        "play",
        "reaction",
        "attack",
        "gain",
        "topdeck_hand",
        "bandit_discard",
        "library",
        "sentry_trash",
        "sentry_discard",
        "sentry_order",
    }
)
_DECISION_EFFECTS = frozenset(
    {
        "action",
        "buy",
        "reaction",
        "cellar",
        "discard_hand",
        "chapel",
        "mine",
        "moneylender",
        "remodel",
        "gain",
        "harbinger",
        "topdeck_hand",
        "bureaucrat",
        "bandit_trash",
        "library_choice",
        "sentry_trash",
        "sentry_discard",
        "sentry_order",
        "throne",
        "vassal",
    }
)


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


def _serial(identifier: str, prefix: str) -> int:
    if re.fullmatch(prefix + r"[1-9][0-9]*", identifier) is None:
        raise InvalidSnapshot("Invalid generated identifier")
    return int(identifier[1:])


def _validate_effect(state: GameState, effect: Effect, *, pending: bool = False) -> None:
    allowed = _DECISION_EFFECTS if pending else _STACK_EFFECTS
    if effect.kind not in allowed or not 0 <= effect.player < len(state.players):
        raise InvalidSnapshot("Invalid effect kind or player")
    if effect.amount < 0 or effect.selected or effect.target not in {-1, 1}:
        raise InvalidSnapshot("Invalid effect parameters")
    if effect.kind == "gain":
        if effect.card_id not in {"", "hand"}:
            raise InvalidSnapshot("Invalid gain destination")
    elif effect.target != -1:
        raise InvalidSnapshot("Invalid effect target")
    if effect.kind in {"resolve", "play", "reaction", "attack"}:
        if effect.card_id not in CATALOG or "action" not in CATALOG[effect.card_id].types:
            raise InvalidSnapshot("Invalid action continuation")
        if effect.kind in {"reaction", "attack"} and "attack" not in CATALOG[effect.card_id].types:
            raise InvalidSnapshot("Invalid attack continuation")
        card = Card(effect.instance_id, effect.card_id)
        if card not in state.players[state.active_player].in_play:
            raise InvalidSnapshot("Continuation references a card outside play")
    if (
        effect.kind
        not in {
            "reaction",
            "attack",
            "bandit_trash",
            "bandit_discard",
            "bureaucrat",
            "discard_hand",
        }
        and effect.player != state.active_player
    ):
        raise InvalidSnapshot("Continuation is assigned to the wrong player")


def _validate_options(state: GameState, pending: Decision, effect: Effect) -> None:
    """Reject stale or forged references before a restored choice can be applied."""
    player = state.players[pending.player]
    kind = effect.kind
    expected: tuple[Option, ...]
    minimum, maximum = 1, 1
    ordered = False
    decision_kind: DecisionKind = "select"
    prompts = {kind}
    if kind in {"action", "buy"}:
        decision_kind = "menu"
        if pending.player != state.active_player or state.phase != kind:
            raise InvalidSnapshot("Menu does not match the turn phase")
        if kind == "action":
            if state.actions <= 0:
                raise InvalidSnapshot("Action menu has no actions remaining")
            eligible = [card for card in player.hand if "action" in CATALOG[card.definition].types]
            expected = tuple(Option(card.id, card.definition, card.id) for card in eligible) + (
                Option("end-actions"),
            )
        else:
            treasures = (
                []
                if state.buying_started
                else [card for card in player.hand if "treasure" in CATALOG[card.definition].types]
            )
            expected = tuple(Option(card.id, card.definition, card.id) for card in treasures)
            if treasures:
                expected += (Option("play-treasures"),)
            if state.buys:
                expected += tuple(
                    Option(key, key)
                    for key, count in state.supply.items()
                    if count > 0 and CATALOG[key].cost <= state.coins
                )
            expected += (Option("end-turn"),)
    elif kind == "gain":
        decision_kind = "supply"
        prompts = {"gain_hand" if effect.card_id == "hand" else "gain"}
        expected = tuple(
            Option(key, key)
            for key, count in state.supply.items()
            if count > 0
            and CATALOG[key].cost <= effect.amount
            and (effect.target != 1 or "treasure" in CATALOG[key].types)
        )
    elif kind in {"reaction", "vassal", "library_choice"}:
        decision_kind = "yes_no"
        expected = (Option("yes"), Option("no"))
        if kind == "reaction" and not any(card.definition == "k16" for card in player.hand):
            raise InvalidSnapshot("Reaction card is missing")
        if kind in {"vassal", "library_choice"}:
            zone = player.discard if kind == "vassal" else player.looked
            card = next((card for card in zone if card.id == effect.instance_id), None)
            if card is None or "action" not in CATALOG[card.definition].types:
                raise InvalidSnapshot("Optional action is missing")
            if kind == "library_choice":
                prompts = {"library"}
                expected = (Option("yes", card.definition, card.id), Option("no"))
    else:
        zone = (
            player.discard
            if kind == "harbinger"
            else player.revealed
            if kind == "bandit_trash"
            else player.looked
            if kind.startswith("sentry_")
            else player.hand
        )
        eligible = [
            card
            for card in zone
            if (kind != "mine" or "treasure" in CATALOG[card.definition].types)
            and (kind != "moneylender" or card.definition == "treasure1")
            and (kind != "bureaucrat" or "victory" in CATALOG[card.definition].types)
            and (kind != "throne" or "action" in CATALOG[card.definition].types)
            and (
                kind != "bandit_trash"
                or ("treasure" in CATALOG[card.definition].types and card.definition != "treasure1")
            )
        ]
        expected = tuple(Option(card.id, card.definition, card.id) for card in eligible)
        if kind in {"cellar", "sentry_trash", "sentry_discard"}:
            minimum, maximum = 0, len(expected)
        elif kind == "chapel":
            minimum, maximum = 0, min(4, len(expected))
        elif kind in {"mine", "moneylender", "throne", "harbinger"}:
            minimum = 0
        elif kind == "discard_hand":
            prompts = {"militia", "poacher"}
            amount = (
                len(player.hand) - 3
                if pending.prompt == "militia"
                else sum(count == 0 for count in state.supply.values())
            )
            minimum = maximum = min(amount, len(expected))
        elif kind == "sentry_order":
            minimum = maximum = len(expected)
            decision_kind = "order"
        elif kind == "bandit_trash":
            prompts = {"bandit"}
        elif kind == "topdeck_hand":
            prompts = {"topdeck"}
        ordered = kind in {"cellar", "discard_hand", "sentry_discard", "sentry_order"}
    if (
        not expected
        or set(pending.options) != set(expected)
        or (pending.minimum, pending.maximum) != (minimum, maximum)
        or pending.kind != decision_kind
        or pending.prompt not in prompts
        or pending.ordered != ordered
    ):
        raise InvalidSnapshot("Decision options or constraints disagree with the continuation")


def _validate(state: GameState) -> None:
    count = len(state.players)
    if (
        not 2 <= count <= 4
        or state.config.player_count != count
        or not 0 <= state.active_player < count
    ):
        raise InvalidSnapshot("Invalid players")
    kingdom = state.config.kingdom
    if (
        len(kingdom) != 10
        or len(set(kingdom)) != 10
        or not set(kingdom) <= set(KINGDOM_IDS)
        or (state.config.player_names and len(state.config.player_names) != count)
    ):
        raise InvalidSnapshot("Invalid game configuration")
    if any(key not in CATALOG or value < 0 for key, value in state.supply.items()):
        raise InvalidSnapshot("Invalid supply")
    if set(state.supply) != set(kingdom) | (set(CATALOG) - set(KINGDOM_IDS)):
        raise InvalidSnapshot("Supply does not match the configured game")
    if (
        "victory3" not in state.supply
        or min(state.actions, state.buys, state.coins, state.revision) < 0
    ):
        raise InvalidSnapshot("Invalid turn state")
    cards = state.trash + [card for player in state.players for card in all_cards(player)]
    if len({card.id for card in cards}) != len(cards):
        raise InvalidSnapshot("A card occurs in more than one zone")
    if state.next_instance_id <= max((_serial(card.id, "c") for card in cards), default=0):
        raise InvalidSnapshot("The next card identifier would reuse an existing card")
    if state.next_decision_id < 1 or state.turn < 1 or not 0 <= state.rng_state < 2**64:
        raise InvalidSnapshot("Invalid sequence or random state")
    if any(player.turns < 0 for player in state.players):
        raise InvalidSnapshot("Invalid completed turn count")
    if (state.pending is None) != (state.pending_effect is None):
        raise InvalidSnapshot("Decision and continuation disagree")
    if state.phase == "finished" and (state.pending is not None or state.effects):
        raise InvalidSnapshot("Finished game has unresolved decisions")
    if state.pending is not None:
        pending = state.pending
        if not 0 <= pending.player < count or not 0 <= pending.minimum <= pending.maximum <= len(
            pending.options
        ):
            raise InvalidSnapshot("Invalid decision bounds")
        if len({option.id for option in pending.options}) != len(pending.options):
            raise InvalidSnapshot("Duplicate decision option")
        if state.next_decision_id <= _serial(pending.id, "d"):
            raise InvalidSnapshot("The next decision identifier would be reused")
        continuation = state.pending_effect
        assert continuation is not None
        if continuation.player != pending.player:
            raise InvalidSnapshot("Decision and continuation owners disagree")
        _validate_effect(state, continuation, pending=True)
        _validate_options(state, pending, continuation)
    for effect in state.effects:
        _validate_effect(state, effect)
    if any(
        not 0 <= event.player < count
        or (event.audience is not None and not 0 <= event.audience < count)
        for event in state.events
    ):
        raise InvalidSnapshot("Invalid event audience or player")
    if state.phase != "finished" and state.pending is None:
        raise InvalidSnapshot("Unfinished game has no pending decision")
    if state.phase == "finished" and (
        len(state.scores) != count
        or not state.winners
        or any(not 0 <= winner < count for winner in state.winners)
    ):
        raise InvalidSnapshot("Invalid game results")


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
