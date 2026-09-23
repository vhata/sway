"""Reproducible heuristic opponents using only the same view humans receive."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from random import Random
from typing import Protocol

from sway.engine.catalog import CATALOG
from sway.engine.models import Command, Decision, Option, PlayerView

STRATEGIES = ("economy", "engine", "attack")
_VERSION = 1
_MASK = (1 << 64) - 1
_SUPPORT = frozenset({"k07", "k24"})
_CANTRIPS = frozenset({"k04", "k09", "k10", "k12", "k13", "k18", "k20"})


@dataclass(frozen=True)
class BotState:
    profile: str
    seed: int
    decisions: int = 0
    version: int = _VERSION


@dataclass(frozen=True)
class BotChoice:
    command: Command
    state: BotState


class Strategy(Protocol):
    def purchase_value(self, view: PlayerView, card_id: str, owned: Counter[str]) -> float:
        """Rank a legal gain without access to authoritative game state."""
        ...


@dataclass(frozen=True)
class HeuristicStrategy:
    profile: str
    action_weights: dict[str, float]
    gold_weight: float
    silver_weight: float

    def purchase_value(self, view: PlayerView, card_id: str, owned: Counter[str]) -> float:
        provinces = view.supply.get("victory3", 0)
        if card_id == "victory3":
            return 1000
        if card_id == "victory2":
            return 95 if provinces <= 4 else -20
        if card_id == "victory1":
            return 75 if provinces <= 2 else -40
        if card_id == "curse":
            return -200
        if card_id == "treasure1":
            return -10
        if card_id == "treasure3":
            return self.gold_weight
        if card_id == "treasure2":
            return self.silver_weight
        if card_id == "k08":
            return 85 if sum(owned.values()) >= 30 and provinces <= 5 else -15
        value = self.action_weights.get(card_id, CATALOG[card_id].cost * 6.0)
        # Strong terminal draws still need action capacity. Extra copies become
        # less desirable while cantrips remain useful in larger engines.
        copies = owned[card_id]
        value -= copies * (8 if card_id in _CANTRIPS else 24)
        terminals = sum(
            count
            for key, count in owned.items()
            if "action" in CATALOG[key].types and key not in _CANTRIPS | _SUPPORT
        )
        capacity = 2 + 2 * sum(owned[key] for key in _SUPPORT)
        if card_id in _SUPPORT:
            value += min(30, max(0, terminals - capacity + 2) * 15)
        elif card_id not in _CANTRIPS:
            value -= max(0, terminals - capacity) * 15
        if card_id == "k25" and view.supply.get("curse", 0) == 0:
            value -= 25
        if card_id in {"k05", "k17"} and owned["treasure1"] <= 2:
            value -= 50
        return value


STRATEGY_REGISTRY: dict[str, Strategy] = {
    "economy": HeuristicStrategy(
        "economy",
        {
            "k01": 55,
            "k02": 62,
            "k05": 46,
            "k10": 65,
            "k11": 52,
            "k12": 57,
            "k14": 55,
            "k15": 48,
            "k17": 53,
            "k20": 58,
            "k21": 65,
            "k25": 66,
        },
        85,
        45,
    ),
    "engine": HeuristicStrategy(
        "engine",
        {
            "k01": 60,
            "k04": 28,
            "k05": 62,
            "k06": 72,
            "k07": 70,
            "k09": 39,
            "k10": 92,
            "k11": 70,
            "k12": 80,
            "k13": 43,
            "k18": 50,
            "k20": 86,
            "k21": 74,
            "k22": 63,
            "k24": 54,
            "k25": 70,
            "k26": 29,
        },
        68,
        38,
    ),
    "attack": HeuristicStrategy(
        "attack",
        {
            "k02": 86,
            "k03": 58,
            "k05": 55,
            "k07": 58,
            "k10": 71,
            "k12": 68,
            "k14": 79,
            "k16": 42,
            "k20": 69,
            "k21": 58,
            "k24": 48,
            "k25": 99,
        },
        76,
        40,
    ),
}


def _owned(view: PlayerView) -> Counter[str]:
    # Initial contents and subsequent public gains/trashes are known to a human.
    # Never reconstruct hidden ordering or inspect another player's deck.
    result: Counter[str] = Counter({"treasure1": 7, "victory1": 3})
    for event in view.events:
        if event.player == view.player and event.kind in {"gain", "trash"}:
            change = 1 if event.kind == "gain" else -1
            for card in event.cards:
                result[card.definition] += change
    return result


def _action_value(view: PlayerView, card_id: str) -> float:
    actions_in_hand = sum("action" in CATALOG[card.definition].types for card in view.hand)
    if card_id in _SUPPORT:
        return 130 if actions_in_hand > 1 else 70
    if card_id in _CANTRIPS:
        return 110
    if card_id == "k22":
        return 100 if actions_in_hand > 1 else 1
    if card_id == "k05":
        junk = sum(card.definition in {"curse", "victory1"} for card in view.hand)
        return 120 if junk >= 2 and view.supply.get("victory3", 0) > 3 else 15
    return {
        "k25": 95,
        "k02": 90,
        "k06": 85,
        "k21": 80,
        "k11": 75,
        "k14": 70,
        "k17": 65,
        "k15": 60,
        "k01": 55,
        "k19": 45,
    }.get(card_id, 40)


def _keep_value(view: PlayerView, option: Option) -> float:
    if option.card_id is None:
        return 0
    card = CATALOG[option.card_id]
    if "curse" in card.types:
        return -100
    if "victory" in card.types:
        return -90
    if "treasure" in card.types:
        return 10 * card.coins
    if view.active_player == view.player and view.actions == 0:
        return -5
    return _action_value(view, option.card_id)


def _trash_choices(
    view: PlayerView, options: tuple[Option, ...], owned: Counter[str]
) -> list[Option]:
    coins = sum(CATALOG[key].coins * count for key, count in owned.items())
    choices: list[Option] = []
    # Trash curses/early estates before copper, preserving at least five coins
    # of purchasing power instead of emptying the economy in one Chapel.
    for option in sorted(options, key=lambda item: _keep_value(view, item)):
        if option.card_id == "curse" or (
            option.card_id == "victory1" and view.supply.get("victory3", 0) > 3
        ):
            choices.append(option)
        elif option.card_id == "treasure1" and coins > 5:
            choices.append(option)
            coins -= 1
    return choices


def _selections(
    view: PlayerView, decision: Decision, strategy: Strategy, owned: Counter[str], rng: Random
) -> tuple[str, ...]:
    options = list(decision.options)
    rng.shuffle(options)  # Stable private tie breaking; no gameplay RNG access.
    by_id = {option.id: option for option in options}
    prompt = decision.prompt
    if prompt == "buy":
        if "play-treasures" in by_id:
            return ("play-treasures",)
        cards = [
            option
            for option in options
            if option.card_id is not None and option.instance_id is None
        ]
        if cards:
            best = max(
                cards,
                key=lambda item: strategy.purchase_value(view, item.card_id or "curse", owned),
            )
            if strategy.purchase_value(view, best.card_id or "curse", owned) > 0:
                return (best.id,)
        return ("end-turn",)
    if prompt in {"action", "throne"}:
        cards = [option for option in options if option.card_id is not None]
        if cards:
            return (max(cards, key=lambda item: _action_value(view, item.card_id or "curse")).id,)
        return ("end-actions",) if prompt == "action" else ()
    if decision.kind == "yes_no":
        if prompt == "library":
            return ("yes" if view.actions > 0 else "no",)
        return ("yes",)
    if decision.kind == "supply" or prompt in {"gain", "gain_hand"}:
        ranked = sorted(
            options,
            key=lambda item: strategy.purchase_value(view, item.card_id or "curse", owned),
            reverse=True,
        )
        return tuple(option.id for option in ranked[: decision.minimum])
    if prompt in {"chapel", "sentry_trash"}:
        selected = _trash_choices(view, tuple(options), owned)
    elif prompt == "moneylender":
        selected = (
            options[:1]
            if sum(CATALOG[key].coins * count for key, count in owned.items()) > 3
            else []
        )
    elif prompt == "mine":
        selected = [
            option
            for option in options
            if (option.card_id == "treasure2" and view.supply.get("treasure3", 0) > 0)
            or (option.card_id == "treasure1" and view.supply.get("treasure2", 0) > 0)
        ]
        selected.sort(key=lambda item: CATALOG[item.card_id or "curse"].cost, reverse=True)
    elif prompt == "remodel":
        gold = [option for option in options if option.card_id == "treasure3"]
        selected = (
            gold
            if gold and view.supply.get("victory3", 0) > 0
            else sorted(options, key=lambda item: _keep_value(view, item))
        )
    elif prompt in {"cellar", "sentry_discard"}:
        selected = [option for option in options if _keep_value(view, option) < 0]
    elif prompt == "harbinger":
        selected = sorted(
            (option for option in options if _keep_value(view, option) > 0),
            key=lambda item: _keep_value(view, item),
            reverse=True,
        )[:1]
    elif decision.kind == "order":
        selected = sorted(options, key=lambda item: _keep_value(view, item), reverse=True)
    else:
        # Mandatory discards/topdeck/attack losses retain the most useful cards.
        selected = sorted(options, key=lambda item: _keep_value(view, item))[: decision.minimum]
    if len(selected) < decision.minimum:
        selected.extend(option for option in options if option not in selected)
    return tuple(option.id for option in selected[: decision.maximum])


def choose(view: PlayerView, decision: Decision, state: BotState) -> BotChoice:
    """Choose a legal answer from public options and advance private bot memory."""
    if state.profile not in STRATEGY_REGISTRY or state.version != _VERSION or state.decisions < 0:
        raise ValueError("Unsupported bot profile or state version.")
    if decision.player != view.player or view.pending != decision:
        raise ValueError("A bot can answer only its current visible decision.")
    if not 0 <= decision.minimum <= decision.maximum <= len(decision.options):
        raise ValueError("Invalid decision constraints.")
    if len({option.id for option in decision.options}) != len(decision.options):
        raise ValueError("Decision options must have distinct identifiers.")
    rng = Random((state.seed ^ (state.decisions * 0x9E3779B97F4A7C15)) & _MASK)
    selections = _selections(view, decision, STRATEGY_REGISTRY[state.profile], _owned(view), rng)
    if (
        not decision.minimum <= len(selections) <= decision.maximum
        or len(set(selections)) != len(selections)
        or not set(selections) <= {option.id for option in decision.options}
    ):
        raise ValueError("The strategy did not produce a legal decision.")
    return BotChoice(
        Command(decision.id, view.revision, selections),
        replace(state, decisions=state.decisions + 1),
    )
