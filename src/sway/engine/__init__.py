"""Public rules, decisions, views, and snapshot interface."""

from sway.engine.catalog import CATALOG, KINGDOM_IDS
from sway.engine.core import advance, all_cards, new_game, score_player, view_for
from sway.engine.models import (
    Card,
    CardDefinition,
    Command,
    Decision,
    DecisionKind,
    Effect,
    Event,
    GameConfig,
    GameState,
    InvalidCommand,
    OpponentView,
    Option,
    Phase,
    Player,
    PlayerView,
    Transition,
)
from sway.engine.serialization import InvalidSnapshot, state_from_json, state_to_json

__all__ = [
    "CATALOG",
    "KINGDOM_IDS",
    "Card",
    "CardDefinition",
    "Command",
    "Decision",
    "DecisionKind",
    "Effect",
    "Event",
    "GameConfig",
    "GameState",
    "InvalidCommand",
    "InvalidSnapshot",
    "OpponentView",
    "Option",
    "Phase",
    "Player",
    "PlayerView",
    "Transition",
    "advance",
    "all_cards",
    "new_game",
    "score_player",
    "state_from_json",
    "state_to_json",
    "view_for",
]
