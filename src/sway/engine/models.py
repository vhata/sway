"""Serializable rules state and the presentation-neutral public engine contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

type Phase = Literal["action", "buy", "finished"]
type DecisionKind = Literal["select", "supply", "yes_no", "order", "menu"]


@dataclass(frozen=True)
class CardDefinition:
    id: str
    cost: int
    types: frozenset[str]
    coins: int = 0
    points: int = 0


@dataclass(frozen=True)
class Card:
    id: str
    definition: str


@dataclass(frozen=True)
class GameConfig:
    player_count: int = 2
    kingdom: tuple[str, ...] = (
        "k04", "k12", "k13", "k14", "k15", "k16", "k19", "k21", "k24", "k26"
    )
    player_names: tuple[str, ...] = ()


@dataclass
class Player:
    name: str
    deck: list[Card] = field(default_factory=list)
    hand: list[Card] = field(default_factory=list)
    discard: list[Card] = field(default_factory=list)
    in_play: list[Card] = field(default_factory=list)
    revealed: list[Card] = field(default_factory=list)
    looked: list[Card] = field(default_factory=list)
    set_aside: list[Card] = field(default_factory=list)
    turns: int = 0


@dataclass(frozen=True)
class Option:
    id: str
    card_id: str | None = None
    instance_id: str | None = None


@dataclass(frozen=True)
class Decision:
    id: str
    player: int
    kind: DecisionKind
    prompt: str
    options: tuple[Option, ...]
    minimum: int
    maximum: int
    ordered: bool = False


@dataclass(frozen=True)
class Command:
    decision_id: str
    expected_revision: int
    selections: tuple[str, ...]


@dataclass(frozen=True)
class Effect:
    kind: str
    player: int
    amount: int = 0
    card_id: str = ""
    instance_id: str = ""
    target: int = -1
    selected: tuple[str, ...] = ()


@dataclass(frozen=True)
class Event:
    kind: str
    player: int
    cards: tuple[Card, ...] = ()
    amount: int = 0
    audience: int | None = None


@dataclass
class GameState:
    config: GameConfig
    seed: int
    rng_state: int
    players: list[Player]
    supply: dict[str, int]
    trash: list[Card] = field(default_factory=list)
    active_player: int = 0
    phase: Phase = "action"
    actions: int = 1
    buys: int = 1
    coins: int = 0
    revision: int = 0
    turn: int = 1
    pending: Decision | None = None
    pending_effect: Effect | None = None
    effects: list[Effect] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    next_instance_id: int = 1
    next_decision_id: int = 1
    merchant_bonus: int = 0
    silver_played: bool = False
    buying_started: bool = False
    scores: tuple[int, ...] = ()
    winners: tuple[int, ...] = ()


@dataclass(frozen=True)
class OpponentView:
    name: str
    hand_count: int
    deck_count: int | None
    discard_count: int | None
    discard: tuple[Card, ...]
    in_play: tuple[Card, ...]
    revealed: tuple[Card, ...]
    turns: int


@dataclass(frozen=True)
class PlayerView:
    player: int
    players: tuple[OpponentView, ...]
    hand: tuple[Card, ...]
    looked: tuple[Card, ...]
    supply: dict[str, int]
    trash: tuple[Card, ...]
    active_player: int
    phase: Phase
    actions: int
    buys: int
    coins: int
    revision: int
    turn: int
    pending: Decision | None
    decision_owner: int | None
    events: tuple[Event, ...]
    scores: tuple[int, ...]
    winners: tuple[int, ...]


@dataclass(frozen=True)
class Transition:
    state: GameState
    events: tuple[Event, ...]


class InvalidCommand(ValueError):
    """The submitted decision is stale or its selected options are illegal."""
