"""Deterministic base-set rules with explicit, resumable effect resolution.

Deck tops are at the end of their lists. Effects execute from the end of the
stack; ``_schedule`` accepts effects in their natural execution order.
"""

from __future__ import annotations

from copy import deepcopy

from sway.engine.catalog import CATALOG, KINGDOM_IDS
from sway.engine.models import (
    Card,
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
    Player,
    PlayerView,
    Transition,
)

_MASK = (1 << 64) - 1


def _random_below(state: GameState, bound: int) -> int:
    """SplitMix64 and rejection sampling, stable across Python versions."""
    limit = (1 << 64) - ((1 << 64) % bound)
    while True:
        state.rng_state = (state.rng_state + 0x9E3779B97F4A7C15) & _MASK
        value = state.rng_state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & _MASK
        value ^= value >> 31
        if value < limit:
            return value % bound


def _shuffle(state: GameState, cards: list[Card]) -> None:
    for index in range(len(cards) - 1, 0, -1):
        other = _random_below(state, index + 1)
        cards[index], cards[other] = cards[other], cards[index]


def _card(state: GameState, definition: str) -> Card:
    card = Card(f"c{state.next_instance_id}", definition)
    state.next_instance_id += 1
    return card


def _take_deck(state: GameState, player: int, count: int) -> list[Card]:
    owner = state.players[player]
    # Shuffle before the draw if needed, retaining the existing deck on top.
    if len(owner.deck) < count and owner.discard:
        _shuffle(state, owner.discard)
        owner.deck = owner.discard + owner.deck
        owner.discard = []
        state.events.append(Event("shuffle", player))
    cards: list[Card] = []
    for _ in range(min(count, len(owner.deck))):
        cards.append(owner.deck.pop())
    return cards


def _draw(state: GameState, player: int, count: int) -> None:
    cards = _take_deck(state, player, count)
    state.players[player].hand.extend(cards)
    if cards:
        state.events.append(Event("draw", player, tuple(cards), len(cards), player))


def _gain(state: GameState, player: int, card_id: str, destination: str = "discard") -> None:
    if state.supply.get(card_id, 0) <= 0:
        return
    state.supply[card_id] -= 1
    card = _card(state, card_id)
    owner = state.players[player]
    zone = (
        owner.hand
        if destination == "hand"
        else owner.deck
        if destination == "deck"
        else owner.discard
    )
    zone.append(card)
    state.events.append(Event("gain", player, (card,)))


def _remove(cards: list[Card], ids: tuple[str, ...]) -> list[Card]:
    by_id = {card.id: card for card in cards}
    removed = [by_id[card_id] for card_id in ids]
    cards[:] = [card for card in cards if card.id not in ids]
    return removed


def _discard(state: GameState, player: int, cards: list[Card], *, public: bool = False) -> None:
    state.players[player].discard.extend(cards)
    if not cards:
        return
    state.events.append(
        Event("discard", player, tuple(cards), len(cards), None if public else player)
    )
    if not public:
        # A player may conceal all discarded cards except the top one.
        state.events.append(Event("discard_top", player, (cards[-1],), len(cards)))


def _trash(state: GameState, player: int, cards: list[Card]) -> None:
    state.trash.extend(cards)
    if cards:
        state.events.append(Event("trash", player, tuple(cards), len(cards)))


def _schedule(state: GameState, *effects: Effect) -> None:
    state.effects.extend(reversed(effects))


def _options(cards: list[Card]) -> tuple[Option, ...]:
    return tuple(Option(card.id, card.definition, card.id) for card in cards)


def _choose(
    state: GameState,
    effect: Effect,
    kind: DecisionKind,
    prompt: str,
    options: tuple[Option, ...],
    minimum: int,
    maximum: int,
    *,
    ordered: bool = False,
) -> None:
    if not options:
        return
    state.pending = Decision(
        f"d{state.next_decision_id}",
        effect.player,
        kind,
        prompt,
        options,
        min(minimum, len(options)),
        min(maximum, len(options)),
        ordered,
    )
    state.next_decision_id += 1
    state.pending_effect = effect


def _others(state: GameState, player: int) -> list[int]:
    return [(player + offset) % len(state.players) for offset in range(1, len(state.players))]


def new_game(config: GameConfig, seed: int) -> GameState:
    """Create a seeded game; the starting player is selected by the game RNG."""
    if not 2 <= config.player_count <= 4:
        raise ValueError("Games require two to four players")
    if len(config.kingdom) != 10 or len(set(config.kingdom)) != 10:
        raise ValueError("Select exactly ten distinct Kingdom piles")
    if any(card_id not in KINGDOM_IDS for card_id in config.kingdom):
        raise ValueError("Unknown Kingdom card")
    if config.player_names and len(config.player_names) != config.player_count:
        raise ValueError("Supply one name per player")
    victory_count = 8 if config.player_count == 2 else 12
    supply = {
        key: victory_count if "victory" in CATALOG[key].types else 10 for key in config.kingdom
    }
    supply.update(
        {
            "treasure1": 60 - 7 * config.player_count,
            "treasure2": 40,
            "treasure3": 30,
            "victory1": victory_count,
            "victory2": victory_count,
            "victory3": victory_count,
            "curse": 10 * (config.player_count - 1),
        }
    )
    names = config.player_names or tuple(
        f"Player {index + 1}" for index in range(config.player_count)
    )
    state = GameState(config, seed, seed & _MASK, [Player(name) for name in names], supply)
    for index, player in enumerate(state.players):
        player.deck = [_card(state, "treasure1") for _ in range(7)]
        player.deck.extend(_card(state, "victory1") for _ in range(3))
        _shuffle(state, player.deck)
        _draw(state, index, 5)
    state.active_player = _random_below(state, config.player_count)
    state.events.append(Event("turn", state.active_player, amount=state.turn))
    _settle(state)
    return state


def advance(state: GameState, command: Command) -> Transition:
    """Validate and apply one decision without modifying the input state."""
    decision = state.pending
    if decision is None or state.pending_effect is None or state.phase == "finished":
        raise InvalidCommand("There is no pending decision")
    if command.expected_revision != state.revision or command.decision_id != decision.id:
        raise InvalidCommand("This decision is stale; reload the current game")
    chosen = command.selections
    if len(set(chosen)) != len(chosen):
        raise InvalidCommand("An option cannot be selected twice")
    if not decision.minimum <= len(chosen) <= decision.maximum:
        raise InvalidCommand("The number of selected options is invalid")
    if not set(chosen).issubset(option.id for option in decision.options):
        raise InvalidCommand("An option is not available for this decision")
    # Events and their cards are immutable. Copy the history list without
    # recursively copying every past event on every future decision.
    updated = deepcopy(state, {id(state.events): list(state.events)})
    old_event_count = len(updated.events)
    effect = updated.pending_effect
    assert effect is not None
    updated.pending = None
    updated.pending_effect = None
    updated.revision += 1
    _answer(updated, effect, chosen)
    _settle(updated)
    return Transition(updated, tuple(updated.events[old_event_count:]))


def view_for(state: GameState, player: int) -> PlayerView:
    """Project authoritative state without hidden zones, RNG, or private effects."""
    if not 0 <= player < len(state.players):
        raise ValueError("Unknown player")
    pending = state.pending
    return PlayerView(
        player=player,
        players=tuple(
            OpponentView(
                owner.name,
                len(owner.hand),
                len(owner.deck) if index == player else None,
                None,
                tuple(owner.discard[-1:]),
                tuple(owner.in_play),
                tuple(owner.revealed),
                owner.turns,
                tuple(owner.set_aside),
            )
            for index, owner in enumerate(state.players)
        ),
        hand=tuple(state.players[player].hand),
        looked=tuple(state.players[player].looked),
        supply=dict(state.supply),
        trash=tuple(state.trash),
        active_player=state.active_player,
        phase=state.phase,
        actions=state.actions,
        buys=state.buys,
        coins=state.coins,
        revision=state.revision,
        turn=state.turn,
        pending=pending if pending is not None and pending.player == player else None,
        decision_owner=pending.player if pending is not None else None,
        events=tuple(event for event in state.events if event.audience in {None, player}),
        scores=state.scores,
        winners=state.winners,
    )


def _settle(state: GameState) -> None:
    while state.pending is None and state.phase != "finished":
        if state.effects:
            _execute(state, state.effects.pop())
        elif state.phase == "action":
            available = [
                card
                for card in state.players[state.active_player].hand
                if "action" in CATALOG[card.definition].types
            ]
            if state.actions <= 0 or not available:
                state.phase = "buy"
                continue
            _choose(
                state,
                Effect("action", state.active_player),
                "menu",
                "action",
                _options(available) + (Option("end-actions"),),
                1,
                1,
            )
        else:
            options: list[Option] = []
            if not state.buying_started:
                treasures = [
                    card
                    for card in state.players[state.active_player].hand
                    if "treasure" in CATALOG[card.definition].types
                ]
                options.extend(_options(treasures))
                if treasures:
                    options.append(Option("play-treasures"))
            if state.buys > 0:
                options.extend(
                    Option(card_id, card_id)
                    for card_id, count in sorted(state.supply.items())
                    if count > 0 and CATALOG[card_id].cost <= state.coins
                )
            options.append(Option("end-turn"))
            _choose(state, Effect("buy", state.active_player), "menu", "buy", tuple(options), 1, 1)


def _play_treasure(state: GameState, player: int, card: Card) -> None:
    state.players[player].hand.remove(card)
    state.players[player].in_play.append(card)
    state.coins += CATALOG[card.definition].coins
    if card.definition == "treasure2" and not state.silver_played:
        state.coins += state.merchant_bonus
        state.silver_played = True
    state.events.append(Event("play", player, (card,)))


def _play(state: GameState, player: int, card: Card) -> None:
    state.events.append(Event("play", player, (card,)))
    resolve = Effect("resolve", player, card_id=card.definition, instance_id=card.id)
    if "attack" in CATALOG[card.definition].types:
        others = _others(state, player)
        _schedule(
            state,
            *(
                Effect("reaction", target, card_id=card.definition, instance_id=card.id)
                for target in others
            ),
            resolve,
            *(
                Effect("attack", target, card_id=card.definition, instance_id=card.id)
                for target in others
            ),
        )
    else:
        _schedule(state, resolve)


def _finish_turn(state: GameState) -> None:
    player = state.players[state.active_player]
    _discard(state, state.active_player, player.hand + player.in_play)
    player.hand = []
    player.in_play = []
    _draw(state, state.active_player, 5)
    player.turns += 1
    if state.supply["victory3"] == 0 or sum(count == 0 for count in state.supply.values()) >= 3:
        state.phase = "finished"
        state.scores = tuple(score_player(owner) for owner in state.players)
        best = max(state.scores)
        fewest_turns = min(
            owner.turns for index, owner in enumerate(state.players) if state.scores[index] == best
        )
        state.winners = tuple(
            index
            for index, owner in enumerate(state.players)
            if state.scores[index] == best and owner.turns == fewest_turns
        )
        state.events.append(Event("game_over", state.active_player))
        return
    state.active_player = (state.active_player + 1) % len(state.players)
    state.turn += 1
    state.phase = "action"
    state.actions, state.buys, state.coins = 1, 1, 0
    state.merchant_bonus = 0
    state.silver_played = False
    state.buying_started = False
    state.events.append(Event("turn", state.active_player, amount=state.turn))


def all_cards(player: Player) -> list[Card]:
    return (
        player.deck
        + player.hand
        + player.discard
        + player.in_play
        + player.revealed
        + player.looked
        + player.set_aside
    )


def score_player(player: Player) -> int:
    cards = all_cards(player)
    return sum(
        len(cards) // 10 if card.definition == "k08" else CATALOG[card.definition].points
        for card in cards
    )


def _resolve_card(state: GameState, effect: Effect) -> None:
    actor = effect.player
    card_id = effect.card_id
    player = state.players[actor]
    # Immediate bonuses happen before the card's remaining instructions.
    draws = {
        "k06": 4,
        "k09": 1,
        "k10": 2,
        "k12": 1,
        "k13": 1,
        "k16": 2,
        "k18": 1,
        "k20": 1,
        "k21": 3,
        "k24": 1,
        "k25": 2,
    }
    actions = {
        "k04": 1,
        "k07": 2,
        "k09": 1,
        "k10": 1,
        "k12": 1,
        "k13": 1,
        "k18": 1,
        "k20": 1,
        "k24": 2,
    }
    _draw(state, actor, draws.get(card_id, 0))
    state.actions += actions.get(card_id, 0)
    state.buys += int(card_id in {"k06", "k07", "k12"})
    state.coins += {"k07": 2, "k12": 1, "k14": 2, "k18": 1, "k23": 2}.get(card_id, 0)
    if card_id == "k01":
        _schedule(state, Effect("gain", actor, 5, "hand"), Effect("topdeck_hand", actor))
    elif card_id == "k02":
        _gain(state, actor, "treasure3")
    elif card_id == "k03":
        _gain(state, actor, "treasure2", "deck")
    elif card_id == "k04":
        _choose(
            state,
            Effect("cellar", actor),
            "select",
            "cellar",
            _options(player.hand),
            0,
            len(player.hand),
            ordered=True,
        )
    elif card_id == "k05":
        _choose(state, Effect("chapel", actor), "select", "chapel", _options(player.hand), 0, 4)
    elif card_id == "k06":
        for other in _others(state, actor):
            _draw(state, other, 1)
    elif card_id == "k09":
        _choose(
            state, Effect("harbinger", actor), "select", "harbinger", _options(player.discard), 0, 1
        )
    elif card_id == "k11":
        _schedule(state, Effect("library", actor))
    elif card_id == "k13":
        state.merchant_bonus += 1
    elif card_id == "k15":
        choices = [card for card in player.hand if "treasure" in CATALOG[card.definition].types]
        _choose(state, Effect("mine", actor), "select", "mine", _options(choices), 0, 1)
    elif card_id == "k17":
        choices = [card for card in player.hand if card.definition == "treasure1"]
        _choose(
            state, Effect("moneylender", actor), "select", "moneylender", _options(choices), 0, 1
        )
    elif card_id == "k18":
        count = sum(value == 0 for value in state.supply.values())
        if count:
            _choose(
                state,
                Effect("discard_hand", actor),
                "select",
                "poacher",
                _options(player.hand),
                count,
                count,
                ordered=True,
            )
    elif card_id == "k19":
        _choose(state, Effect("remodel", actor), "select", "remodel", _options(player.hand), 1, 1)
    elif card_id == "k20":
        player.looked.extend(_take_deck(state, actor, 2))
        _schedule(
            state,
            Effect("sentry_trash", actor),
            Effect("sentry_discard", actor),
            Effect("sentry_order", actor),
        )
    elif card_id == "k22":
        choices = [card for card in player.hand if "action" in CATALOG[card.definition].types]
        _choose(state, Effect("throne", actor), "select", "throne", _options(choices), 0, 1)
    elif card_id == "k23":
        cards = _take_deck(state, actor, 1)
        _discard(state, actor, cards, public=True)
        if cards and "action" in CATALOG[cards[0].definition].types:
            _choose(
                state,
                Effect("vassal", actor, instance_id=cards[0].id),
                "yes_no",
                "vassal",
                (Option("yes"), Option("no")),
                1,
                1,
            )
    elif card_id == "k26":
        _schedule(state, Effect("gain", actor, 4))


def _execute(state: GameState, effect: Effect) -> None:
    player = state.players[effect.player]
    actor = effect.player
    kind = effect.kind
    if kind == "resolve":
        _resolve_card(state, effect)
    elif kind == "play":
        _play(state, actor, Card(effect.instance_id, effect.card_id))
    elif kind == "reaction":
        if any(card.definition == "k16" for card in player.hand):
            _choose(state, effect, "yes_no", "reaction", (Option("yes"), Option("no")), 1, 1)
    elif kind == "attack":
        _attack(state, effect)
    elif kind == "gain":
        options = tuple(
            Option(key, key)
            for key, count in sorted(state.supply.items())
            if count > 0
            and CATALOG[key].cost <= effect.amount
            and (effect.target != 1 or "treasure" in CATALOG[key].types)
        )
        _choose(
            state,
            effect,
            "supply",
            "gain_hand" if effect.card_id == "hand" else "gain",
            options,
            1,
            1,
        )
    elif kind == "topdeck_hand":
        _choose(state, effect, "select", "topdeck", _options(player.hand), 1, 1)
    elif kind == "bandit_discard":
        _discard(state, actor, player.revealed, public=True)
        player.revealed = []
    elif kind == "library":
        _library(state, effect)
    elif kind == "sentry_trash":
        _choose(state, effect, "select", kind, _options(player.looked), 0, len(player.looked))
    elif kind == "sentry_discard":
        _choose(
            state,
            effect,
            "select",
            kind,
            _options(player.looked),
            0,
            len(player.looked),
            ordered=True,
        )
    elif kind == "sentry_order":
        _choose(
            state,
            effect,
            "order",
            kind,
            _options(player.looked),
            len(player.looked),
            len(player.looked),
            ordered=True,
        )
    else:
        raise ValueError(f"Unknown effect: {kind}")


def _attack(state: GameState, effect: Effect) -> None:
    actor = effect.player
    player = state.players[actor]
    if effect.card_id == "k02":
        player.revealed.extend(_take_deck(state, actor, 2))
        state.events.append(Event("reveal", actor, tuple(player.revealed)))
        eligible = [
            card
            for card in player.revealed
            if "treasure" in CATALOG[card.definition].types and card.definition != "treasure1"
        ]
        _schedule(state, Effect("bandit_discard", actor))
        _choose(state, Effect("bandit_trash", actor), "select", "bandit", _options(eligible), 1, 1)
    elif effect.card_id == "k03":
        eligible = [card for card in player.hand if "victory" in CATALOG[card.definition].types]
        if eligible:
            _choose(
                state, Effect("bureaucrat", actor), "select", "bureaucrat", _options(eligible), 1, 1
            )
        else:
            state.events.append(Event("reveal", actor, tuple(player.hand)))
    elif effect.card_id == "k14":
        count = len(player.hand) - 3
        if count > 0:
            _choose(
                state,
                Effect("discard_hand", actor),
                "select",
                "militia",
                _options(player.hand),
                count,
                count,
                ordered=True,
            )
    elif effect.card_id == "k25":
        _gain(state, actor, "curse")


def _library(state: GameState, effect: Effect) -> None:
    actor = effect.player
    player = state.players[actor]
    while len(player.hand) < 7:
        cards = _take_deck(state, actor, 1)
        if not cards:
            break
        card = cards[0]
        if "action" in CATALOG[card.definition].types:
            player.looked.append(card)
            _choose(
                state,
                Effect("library_choice", actor, instance_id=card.id),
                "yes_no",
                "library",
                (Option("yes", card.definition, card.id), Option("no")),
                1,
                1,
            )
            return
        player.hand.append(card)
        state.events.append(Event("draw", actor, (card,), 1, actor))
    _discard(state, actor, player.set_aside)
    player.set_aside = []


def _answer(state: GameState, effect: Effect, selected: tuple[str, ...]) -> None:
    actor = effect.player
    player = state.players[actor]
    kind = effect.kind
    if kind == "action":
        if selected[0] == "end-actions":
            state.phase = "buy"
        else:
            card = _remove(player.hand, selected)[0]
            player.in_play.append(card)
            state.actions -= 1
            _play(state, actor, card)
    elif kind == "buy":
        option = selected[0]
        if option == "end-turn":
            _finish_turn(state)
        elif option == "play-treasures":
            for card in list(player.hand):
                if "treasure" in CATALOG[card.definition].types:
                    _play_treasure(state, actor, card)
        elif option in state.supply:
            state.coins -= CATALOG[option].cost
            state.buys -= 1
            state.buying_started = True
            _gain(state, actor, option)
        else:
            card = next(card for card in player.hand if card.id == option)
            _play_treasure(state, actor, card)
    elif kind == "reaction":
        if selected[0] == "yes":
            moat = next(card for card in player.hand if card.definition == "k16")
            state.events.append(Event("block", actor, (moat,)))
            state.effects = [
                item
                for item in state.effects
                if not (
                    item.kind == "attack"
                    and item.player == actor
                    and item.instance_id == effect.instance_id
                )
            ]
    elif kind in {"cellar", "discard_hand"}:
        cards = _remove(player.hand, selected)
        _discard(state, actor, cards)
        if kind == "cellar":
            _draw(state, actor, len(cards))
    elif kind in {"chapel", "mine", "moneylender", "remodel"}:
        cards = _remove(player.hand, selected)
        _trash(state, actor, cards)
        if cards:
            if kind == "moneylender":
                state.coins += 3
            elif kind in {"mine", "remodel"}:
                amount = CATALOG[cards[0].definition].cost + (3 if kind == "mine" else 2)
                _schedule(
                    state,
                    Effect(
                        "gain",
                        actor,
                        amount,
                        "hand" if kind == "mine" else "",
                        target=1 if kind == "mine" else -1,
                    ),
                )
    elif kind == "gain":
        _gain(state, actor, selected[0], effect.card_id)
    elif kind in {"harbinger", "topdeck_hand", "bureaucrat"}:
        source = player.discard if kind == "harbinger" else player.hand
        cards = _remove(source, selected)
        player.deck.extend(cards)
        if cards:
            state.events.append(
                Event(
                    "topdeck",
                    actor,
                    tuple(cards),
                    len(cards),
                    None if kind == "bureaucrat" else actor,
                )
            )
    elif kind == "bandit_trash":
        _trash(state, actor, _remove(player.revealed, selected))
    elif kind == "library_choice":
        card = _remove(player.looked, (effect.instance_id,))[0]
        if selected[0] == "yes":
            player.hand.append(card)
            state.events.append(Event("draw", actor, (card,), 1, actor))
        else:
            player.set_aside.append(card)
            state.events.append(Event("set_aside", actor, (card,)))
        _schedule(state, Effect("library", actor))
    elif kind == "sentry_trash":
        _trash(state, actor, _remove(player.looked, selected))
    elif kind == "sentry_discard":
        _discard(state, actor, _remove(player.looked, selected))
    elif kind == "sentry_order":
        # The first submitted card is the next card to be drawn.
        cards = _remove(player.looked, selected)
        player.deck.extend(reversed(cards))
        state.events.append(Event("topdeck", actor, tuple(cards), len(cards), actor))
    elif kind == "throne":
        if selected:
            card = _remove(player.hand, selected)[0]
            player.in_play.append(card)
            _schedule(
                state,
                Effect("play", actor, card_id=card.definition, instance_id=card.id),
                Effect("play", actor, card_id=card.definition, instance_id=card.id),
            )
    elif kind == "vassal":
        if selected[0] == "yes":
            card = _remove(player.discard, (effect.instance_id,))[0]
            player.in_play.append(card)
            _play(state, actor, card)
    else:
        raise ValueError(f"Unknown decision effect: {kind}")
