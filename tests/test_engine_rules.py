"""Rule examples specify outcomes independently of card implementation."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from sway.engine import (
    CATALOG,
    Card,
    Command,
    Decision,
    Effect,
    GameConfig,
    GameState,
    InvalidCommand,
    Option,
    Player,
    advance,
    all_cards,
    new_game,
    score_player,
    state_from_json,
    state_to_json,
    view_for,
)


def cards(state: GameState, *definitions: str) -> list[Card]:
    result: list[Card] = []
    for definition in definitions:
        result.append(Card(f"c{state.next_instance_id}", definition))
        state.next_instance_id += 1
    return result


def scenario(
    *hand: str,
    deck: tuple[str, ...] = (),
    discard: tuple[str, ...] = (),
    opponent: tuple[str, ...] = (),
    opponents: int = 1,
) -> GameState:
    state = GameState(
        GameConfig(player_count=opponents + 1),
        10,
        10,
        [Player(f"P{i}") for i in range(opponents + 1)],
        {key: 10 for key in CATALOG},
    )
    state.players[0].hand = cards(state, *hand)
    state.players[0].deck = list(reversed(cards(state, *deck)))
    state.players[0].discard = cards(state, *discard)
    for player in state.players[1:]:
        player.hand = cards(state, *opponent)
    action_options = tuple(
        Option(card.id, card.definition, card.id)
        for card in state.players[0].hand
        if "action" in CATALOG[card.definition].types
    )
    state.pending = Decision(
        "setup", 0, "menu", "action", action_options + (Option("end-actions"),), 1, 1
    )
    state.pending_effect = Effect("action", 0)
    return state


def choose(state: GameState, *selected: str) -> GameState:
    assert state.pending is not None
    return advance(state, Command(state.pending.id, state.revision, tuple(selected))).state


def play(state: GameState, definition: str) -> GameState:
    card = next(
        card for card in state.players[state.active_player].hand if card.definition == definition
    )
    return choose(state, card.id)


def select_definitions(state: GameState, *definitions: str) -> GameState:
    assert state.pending is not None
    remaining = list(state.pending.options)
    selected: list[str] = []
    for definition in definitions:
        option = next(option for option in remaining if option.card_id == definition)
        remaining.remove(option)
        selected.append(option.id)
    return choose(state, *selected)


def definitions(zone: list[Card]) -> list[str]:
    return [card.definition for card in zone]


@pytest.mark.parametrize(
    "player_count,victories,curses,copper", [(2, 8, 10, 46), (3, 12, 20, 39), (4, 12, 30, 32)]
)
def test_initial_supply_and_decks(
    player_count: int, victories: int, curses: int, copper: int
) -> None:
    kingdom = ("k08", *GameConfig().kingdom[1:])
    state = new_game(GameConfig(player_count, kingdom), 42)
    assert state.supply["victory1"] == state.supply["victory3"] == state.supply["k08"] == victories
    assert state.supply["curse"] == curses
    assert state.supply["treasure1"] == copper
    assert state.supply["treasure2"] == 40
    assert state.supply["treasure3"] == 30
    assert len(state.supply) == 17
    for player in state.players:
        assert len(player.hand) == len(player.deck) == 5
        assert Counter(definitions(all_cards(player))) == {"treasure1": 7, "victory1": 3}
    assert state_to_json(state) == state_to_json(new_game(GameConfig(player_count, kingdom), 42))


@pytest.mark.parametrize(
    "config",
    [
        GameConfig(1),
        GameConfig(5),
        GameConfig(2, ("k01",)),
        GameConfig(2, ("k01",) * 10),
        GameConfig(2, ("unknown", *GameConfig().kingdom[1:])),
        GameConfig(2, player_names=("One",)),
    ],
)
def test_invalid_game_config(config: GameConfig) -> None:
    with pytest.raises(ValueError):
        new_game(config, 1)


@pytest.mark.parametrize(
    "card,draw,actions,buys,coins",
    [
        ("k07", 0, 2, 2, 2),
        ("k10", 2, 1, 1, 0),
        ("k12", 1, 1, 2, 1),
        ("k13", 1, 1, 1, 0),
        ("k16", 2, 0, 1, 0),
        ("k21", 3, 0, 1, 0),
        ("k24", 1, 2, 1, 0),
    ],
)
def test_simple_action_bonuses(card: str, draw: int, actions: int, buys: int, coins: int) -> None:
    state = play(scenario(card, deck=("treasure1",) * 5), card)
    assert len(state.players[0].hand) == draw
    assert (state.actions, state.buys, state.coins) == (actions, buys, coins)
    assert definitions(state.players[0].in_play) == [card]


def test_cellar_discards_before_shuffling_and_allows_zero() -> None:
    state = play(scenario("k04", "victory1", "curse", deck=("treasure3",)), "k04")
    state = select_definitions(state, "victory1", "curse")
    assert len(state.players[0].hand) == 2
    assert state.players[0].hand[0].definition == "treasure3"
    assert len(state.players[0].discard) == 0
    assert len(state.players[0].deck) == 1
    assert state.actions == 1
    assert state.events[-1].kind == "draw"
    skipped = choose(play(scenario("k04", "victory1"), "k04"))
    assert definitions(skipped.players[0].hand) == ["victory1"]
    empty = play(scenario("k04"), "k04")
    assert empty.phase == "buy"


def test_chapel_trashes_up_to_four_and_cannot_trash_itself() -> None:
    state = play(scenario("k05", "curse", "victory1", "treasure1", "treasure1", "treasure3"), "k05")
    assert state.pending is not None and state.pending.maximum == 4
    assert all(option.card_id != "k05" for option in state.pending.options)
    state = select_definitions(state, "curse", "victory1", "treasure1", "treasure1")
    assert len(state.trash) == 4
    assert definitions(state.players[0].hand) == ["treasure3"]
    skipped = choose(play(scenario("k05", "curse"), "k05"))
    assert not skipped.trash


def test_council_room_draws_for_all_opponents_without_attack_reactions() -> None:
    state = scenario("k06", deck=("treasure1",) * 5, opponent=("k16",), opponents=3)
    for owner in state.players[1:]:
        owner.deck = cards(state, "treasure3")
    state = play(state, "k06")
    assert len(state.players[0].hand) == 4
    assert state.buys == 2
    assert all(len(owner.hand) == 2 for owner in state.players[1:])
    assert state.pending is not None and state.pending.player == 0


def test_harbinger_draw_then_optional_discard_recovery() -> None:
    state = play(scenario("k09", deck=("treasure1",), discard=("treasure3", "victory1")), "k09")
    state = select_definitions(state, "treasure3")
    assert state.players[0].deck[-1].definition == "treasure3"
    assert definitions(state.players[0].discard) == ["victory1"]
    empty = play(scenario("k09", discard=("treasure3",)), "k09")
    assert empty.pending is not None and empty.pending.prompt == "buy"
    assert definitions(empty.players[0].hand) == ["treasure3"]
    skipped = choose(play(scenario("k09", deck=("treasure1",), discard=("treasure3",)), "k09"))
    assert definitions(skipped.players[0].discard) == ["treasure3"]


def test_artisan_gains_to_hand_then_topdecks_even_without_gain() -> None:
    state = play(scenario("k01", "victory1"), "k01")
    assert state.pending is not None and state.pending.prompt == "gain_hand"
    assert all(CATALOG[option.id].cost <= 5 for option in state.pending.options)
    state = choose(state, "k25")
    state = select_definitions(state, "k25")
    assert state.players[0].deck[-1].definition == "k25"
    assert definitions(state.players[0].hand) == ["victory1"]
    empty = scenario("k01", "treasure3")
    for key in empty.supply:
        empty.supply[key] = 0
    empty = play(empty, "k01")
    assert empty.pending is not None and empty.pending.prompt == "topdeck"
    empty = select_definitions(empty, "treasure3")
    assert empty.players[0].deck[-1].definition == "treasure3"


def test_workshop_gain_limit_and_empty_supply() -> None:
    state = play(scenario("k26"), "k26")
    assert state.pending is not None
    assert {option.id for option in state.pending.options} == {
        key for key, value in CATALOG.items() if value.cost <= 4
    }
    state = choose(state, "k08")
    assert definitions(state.players[0].discard) == ["k08"]
    empty = scenario("k26")
    empty.supply = {key: 0 if value.cost <= 4 else 10 for key, value in CATALOG.items()}
    assert play(empty, "k26").phase == "buy"


def test_mine_optional_trash_and_cost_restricted_treasure_to_hand() -> None:
    state = play(scenario("k15", "treasure1", "victory1"), "k15")
    assert state.pending is not None and len(state.pending.options) == 1
    state = select_definitions(state, "treasure1")
    assert state.pending is not None
    assert {option.id for option in state.pending.options} == {"treasure1", "treasure2"}
    state = choose(state, "treasure2")
    assert definitions(state.trash) == ["treasure1"]
    assert definitions(state.players[0].hand) == ["victory1", "treasure2"]
    state = choose(state, "play-treasures")
    assert state.coins == 2
    assert not choose(play(scenario("k15", "treasure1"), "k15")).trash
    assert play(scenario("k15", "victory1"), "k15").phase == "buy"


def test_remodel_requires_trashing_then_gains_to_discard() -> None:
    state = play(scenario("k19", "victory1"), "k19")
    assert state.pending is not None and state.pending.minimum == 1
    state = select_definitions(state, "victory1")
    assert state.pending is not None and all(
        CATALOG[option.id].cost <= 4 for option in state.pending.options
    )
    state = choose(state, "k21")
    assert definitions(state.trash) == ["victory1"]
    assert definitions(state.players[0].discard) == ["k21"]
    assert play(scenario("k19"), "k19").phase == "buy"


def test_moneylender_bonus_requires_actually_trashing_copper() -> None:
    state = select_definitions(play(scenario("k17", "treasure1"), "k17"), "treasure1")
    assert state.coins == 3 and definitions(state.trash) == ["treasure1"]
    assert choose(play(scenario("k17", "treasure1"), "k17")).coins == 0
    assert play(scenario("k17", "treasure2"), "k17").coins == 0


def test_poacher_counts_all_empty_piles_after_draw_and_discards_available_hand() -> None:
    state = scenario("k18", "victory1", deck=("treasure1",))
    state.supply["curse"] = state.supply["treasure3"] = state.supply["k18"] = 0
    state = play(state, "k18")
    assert state.pending is not None and state.pending.minimum == state.pending.maximum == 2
    state = select_definitions(state, "victory1", "treasure1")
    assert not state.players[0].hand
    assert state.actions == state.coins == 1
    no_empty = play(scenario("k18", deck=("treasure1",)), "k18")
    assert no_empty.pending is not None and no_empty.pending.prompt == "buy"


def test_library_skips_actions_until_seven_without_reshuffling_set_aside() -> None:
    state = play(
        scenario(
            "k11",
            "treasure1",
            "treasure1",
            "treasure1",
            "treasure1",
            "treasure1",
            deck=("k21",),
            discard=("treasure3", "k24", "treasure2"),
        ),
        "k11",
    )
    assert state.pending is not None and state.pending.prompt == "library"
    assert definitions(state.players[0].looked) == ["k21"]
    state = choose(state, "no")
    while state.pending is not None and state.pending.prompt == "library":
        state = choose(state, "no")
    assert len(state.players[0].hand) == 7
    assert "k21" in definitions(state.players[0].discard)
    assert not state.players[0].looked and not state.players[0].set_aside
    assert "k21" not in definitions(state.players[0].hand)


def test_library_can_keep_actions_stop_when_empty_or_draw_nothing_at_seven() -> None:
    state = choose(play(scenario("k11", deck=("k21",)), "k11"), "yes")
    assert definitions(state.players[0].hand) == ["k21"]
    assert not state.players[0].discard
    already = play(scenario("k11", *("treasure1",) * 7, deck=("treasure3",)), "k11")
    assert len(already.players[0].hand) == 7 and len(already.players[0].deck) == 1
    empty = choose(play(scenario("k11", deck=("k21",)), "k11"), "no")
    assert definitions(empty.players[0].discard) == ["k21"]


def test_sentry_trash_discard_and_private_order_top_first() -> None:
    state = play(scenario("k20", deck=("treasure1", "curse", "victory1", "treasure3")), "k20")
    assert definitions(state.players[0].hand) == ["treasure1"]
    assert definitions(state.players[0].looked) == ["curse", "victory1"]
    assert view_for(state, 1).looked == ()
    state = select_definitions(state, "curse")
    state = select_definitions(state, "victory1")
    assert definitions(state.trash) == ["curse"]
    assert definitions(state.players[0].discard) == ["victory1"]
    assert not state.players[0].looked
    ordered = play(scenario("k20", deck=("treasure1", "treasure2", "treasure3")), "k20")
    ordered = choose(choose(ordered))
    ordered = select_definitions(ordered, "treasure3", "treasure2")
    assert definitions(ordered.players[0].deck) == ["treasure2", "treasure3"]
    assert play(scenario("k20"), "k20").phase == "buy"


def test_vassal_discards_then_optionally_plays_without_action_cost() -> None:
    state = choose(play(scenario("k23", deck=("k24", "treasure1")), "k23"), "yes")
    assert state.coins == state.actions == 2
    assert definitions(state.players[0].in_play) == ["k23", "k24"]
    assert definitions(state.players[0].hand) == ["treasure1"]
    declined = choose(play(scenario("k23", deck=("k24",)), "k23"), "no")
    assert definitions(declined.players[0].discard) == ["k24"]
    ordinary = play(scenario("k23", deck=("treasure3",)), "k23")
    assert definitions(ordinary.players[0].discard) == ["treasure3"]
    assert play(scenario("k23"), "k23").coins == 2


def test_nested_throne_room_finishes_each_selected_action_twice() -> None:
    state = play(scenario("k22", "k22", "k24", "k21", deck=("treasure1",) * 10), "k22")
    state = select_definitions(state, "k22")
    state = select_definitions(state, "k24")
    assert len(state.players[0].hand) == 3  # Smithy and two draws.
    assert state.actions == 4
    assert state.pending is not None and state.pending.prompt == "throne"
    state = select_definitions(state, "k21")
    assert len(state.players[0].hand) == 8
    assert definitions(state.players[0].in_play) == ["k22", "k22", "k24", "k21"]
    assert state.actions == 4
    optional = choose(play(scenario("k22", "k21"), "k22"))
    assert definitions(optional.players[0].hand) == ["k21"]
    assert play(scenario("k22"), "k22").phase == "buy"


def test_merchant_stacks_per_play_but_only_on_first_silver() -> None:
    state = play(scenario("k22", "k13", "treasure2", "treasure2", deck=("treasure1",) * 2), "k22")
    state = select_definitions(state, "k13")
    assert state.merchant_bonus == 2
    state = choose(state, "play-treasures")
    assert state.coins == 8  # Two silver, two copper, two Merchant bonuses.
    assert state.silver_played


@pytest.mark.parametrize("attack", ["k02", "k03", "k14", "k25"])
def test_moat_reacts_before_attack_benefits_and_blocks_only_its_owner(attack: str) -> None:
    state = scenario(
        attack,
        deck=("treasure1",) * 3,
        opponent=("k16", "victory1", "treasure1", "treasure1"),
        opponents=2,
    )
    state.players[2].hand = cards(state, "treasure1", "treasure1", "treasure1", "victory1")
    state = play(state, attack)
    assert (
        state.pending is not None
        and state.pending.player == 1
        and state.pending.prompt == "reaction"
    )
    assert not state.players[0].discard and not state.players[0].hand and state.coins == 0
    state = choose(state, "yes")
    assert len(state.players[1].hand) == 4
    assert not state.players[1].discard
    assert state.players[1].hand[0].definition == "k16"
    if attack == "k03":
        state = select_definitions(state, "victory1")
        assert state.players[2].deck[-1].definition == "victory1"
    elif attack == "k14":
        state = select_definitions(state, "victory1")
        assert len(state.players[2].hand) == 3
    elif attack == "k25":
        assert definitions(state.players[2].discard) == ["curse"]
        assert len(state.players[0].hand) == 2
    assert any(event.kind == "block" for event in state.events)


def test_declining_moat_and_repeated_attack_each_get_reaction() -> None:
    state = play(scenario("k22", "k25", opponent=("k16",)), "k22")
    state = select_definitions(state, "k25")
    state = choose(state, "no")
    assert definitions(state.players[1].discard) == ["curse"]
    assert state.pending is not None and state.pending.prompt == "reaction"
    state = choose(state, "yes")
    assert definitions(state.players[1].discard) == ["curse"]


def test_witch_curses_in_turn_order_and_continues_when_pile_empty() -> None:
    state = scenario("k25", opponents=3)
    state.supply["curse"] = 1
    state = play(state, "k25")
    assert definitions(state.players[1].discard) == ["curse"]
    assert not state.players[2].discard and not state.players[3].discard
    assert state.supply["curse"] == 0


def test_bandit_victim_chooses_treasure_copper_safe_remaining_cards_discarded() -> None:
    state = scenario("k02")
    state.players[1].deck = cards(state, "treasure2", "treasure3")
    state = play(state, "k02")
    assert definitions(state.players[0].discard) == ["treasure3"]
    assert state.pending is not None and state.pending.player == 1
    state = select_definitions(state, "treasure2")
    assert definitions(state.trash) == ["treasure2"]
    assert definitions(state.players[1].discard) == ["treasure3"]
    assert not state.players[1].revealed
    safe = scenario("k02")
    safe.players[1].deck = cards(safe, "treasure1", "victory1")
    safe = play(safe, "k02")
    assert not safe.trash and len(safe.players[1].discard) == 2
    assert not safe.players[1].revealed


def test_bureaucrat_reveals_no_victory_hand_and_curse_is_not_victory() -> None:
    state = play(scenario("k03", opponent=("curse", "treasure1")), "k03")
    assert state.players[0].deck[-1].definition == "treasure2"
    assert not state.players[1].deck
    reveal = next(event for event in state.events if event.kind == "reveal")
    assert tuple(card.definition for card in reveal.cards) == ("curse", "treasure1")


def test_militia_does_nothing_to_small_hands() -> None:
    state = play(scenario("k14", opponent=("treasure1", "treasure1", "victory1")), "k14")
    assert len(state.players[1].hand) == 3 and not state.players[1].discard
    assert state.coins == 2


def test_buy_phase_individual_treasures_multiple_buys_and_no_treasure_after_purchase() -> None:
    state = choose(scenario("treasure1", "treasure2", "treasure3"), "end-actions")
    copper = state.players[0].hand[0].id
    state = choose(state, copper)
    assert state.coins == 1
    state.buys = 2
    state = choose(state, "curse")
    assert state.buying_started
    assert state.pending is not None and "play-treasures" not in {
        option.id for option in state.pending.options
    }
    assert all(option.instance_id is None for option in state.pending.options)
    state = choose(state, "treasure1")
    assert state.buys == 0 and state.coins == 1
    assert state.pending is not None and [option.id for option in state.pending.options] == [
        "end-turn"
    ]
    state = choose(state, "end-turn")
    assert state.active_player == 1 and state.players[0].turns == 1
    assert (state.actions, state.buys, state.coins, state.merchant_bonus) == (1, 1, 0, 0)
    assert not state.buying_started and not state.silver_played


def test_buy_can_be_skipped_and_action_phase_ended_with_actions_left() -> None:
    state = choose(scenario("k21", "treasure1"), "end-actions")
    assert state.phase == "buy"
    assert definitions(state.players[0].hand) == ["k21", "treasure1"]
    state = choose(state, "end-turn")
    assert state.active_player == 1


def test_game_ends_only_at_turn_end_with_scoring_and_fewer_turns_tiebreak() -> None:
    state = choose(scenario("treasure3"), "end-actions")
    state.supply["victory3"] = 0
    assert state.phase == "buy"
    state = choose(state, "end-turn")
    assert state.phase == "finished" and state.scores == (0, 0)
    assert state.winners == (1,)  # Same points, one fewer turn.
    assert state.pending is None
    with pytest.raises(InvalidCommand):
        advance(state, Command("none", state.revision, ("end-turn",)))
    tied = choose(scenario("victory1"), "end-actions")
    tied.players[1].hand = cards(tied, "victory1")
    tied.players[1].turns = 1
    for key in ("curse", "k01", "treasure1"):
        tied.supply[key] = 0
    tied = choose(tied, "end-turn")
    assert tied.winners == (0, 1) and tied.scores == (1, 1)


def test_gardens_scores_all_owned_zones_rounding_down() -> None:
    state = scenario("k08", "k08", "victory3", "victory2", "victory1", "curse")
    state.players[0].deck = cards(state, *("treasure1",) * 10)
    state.players[0].set_aside = cards(state, "treasure1", "treasure1", "treasure1", "treasure1")
    assert score_player(state.players[0]) == 13  # 2 * 2 + 6 + 3 + 1 - 1.
    state.players[0].set_aside.pop()
    assert score_player(state.players[0]) == 11


def test_views_hide_deck_order_counts_discard_contents_and_other_decisions() -> None:
    state = scenario(
        "k20",
        deck=("treasure1", "treasure2", "treasure3"),
        discard=("k01", "k02"),
        opponent=("k25",),
    )
    state.players[1].deck = cards(state, "k05")
    own = view_for(state, 0)
    other = view_for(state, 1)
    assert own.players[0].deck_count == 3 and own.players[1].deck_count is None
    assert all(player.discard_count is None for player in own.players)
    assert own.players[0].discard == (state.players[0].discard[-1],)
    assert other.pending is None and other.decision_owner == 0
    serialized_view = str(asdict(other))
    for card in state.players[0].hand + state.players[0].deck + state.players[0].discard[:-1]:
        assert repr(card.id) not in serialized_view
    state = play(state, "k20")
    assert not view_for(state, 1).looked
    assert all(event.audience in {None, 1} for event in view_for(state, 1).events)
    with pytest.raises(ValueError):
        view_for(state, -1)


def test_private_multi_discard_shows_only_top_card_to_opponents() -> None:
    state = play(scenario("k04", "curse", "victory1", deck=("treasure3", "treasure3")), "k04")
    discarded = list(state.players[0].hand)
    state = select_definitions(state, "curse", "victory1")
    visible = view_for(state, 1)
    assert all(discarded[0] not in event.cards for event in visible.events)
    top = next(event for event in visible.events if event.kind == "discard_top")
    assert top.cards == (discarded[1],) and top.amount == 2


def test_invalid_stale_and_duplicate_commands_do_not_mutate_input() -> None:
    state = new_game(GameConfig(), 17)
    assert state.pending is not None
    original = state_to_json(state)
    command = Command(state.pending.id, state.revision, ("end-turn",))
    invalid = [
        replace(command, expected_revision=-1),
        replace(command, decision_id="old"),
        replace(command, selections=("made-up",)),
        replace(command, selections=()),
        replace(command, selections=("end-turn", "end-turn")),
    ]
    for item in invalid:
        with pytest.raises(InvalidCommand):
            advance(state, item)
        assert state_to_json(state) == original
    updated = advance(state, command).state
    assert state_to_json(state) == original
    with pytest.raises(InvalidCommand):
        advance(updated, command)


@settings(max_examples=30, deadline=None)
@given(
    seed=st.integers(min_value=0, max_value=2**64 - 1),
    choices=st.lists(st.integers(min_value=0, max_value=1000), min_size=10, max_size=60),
)
def test_legal_sequences_conserve_cards_and_replay_after_every_save(
    seed: int, choices: list[int]
) -> None:
    state = new_game(GameConfig(), seed)
    stock = Counter(state.supply)
    for player in state.players:
        stock.update(definitions(all_cards(player)))
    replay = new_game(GameConfig(), seed)
    for choice in choices:
        if state.phase == "finished":
            break
        pending = state.pending
        assert pending is not None
        count = pending.minimum + choice % (pending.maximum - pending.minimum + 1)
        options = list(pending.options)
        offset = choice % len(options)
        options = options[offset:] + options[:offset]
        command = Command(
            pending.id, state.revision, tuple(option.id for option in options[:count])
        )
        state = advance(state_from_json(state_to_json(state)), command).state
        replay = advance(replay, command).state
        assert state_to_json(state) == state_to_json(replay)
        owned = state.trash + [card for player in state.players for card in all_cards(player)]
        assert len({card.id for card in owned}) == len(owned)
        current = Counter(state.supply)
        current.update(definitions(owned))
        assert current == stock
        assert min(state.actions, state.buys, state.coins) >= 0


@pytest.mark.parametrize("attack", ["k02", "k03", "k14", "k25"])
def test_save_resume_preserves_attack_and_nested_effect_continuations(attack: str) -> None:
    state = play(
        scenario("k22", attack, opponent=("k16", "victory1", "treasure1", "treasure1")), "k22"
    )
    state = select_definitions(state, attack)
    restored = state_from_json(state_to_json(state))
    assert choose(restored, "yes") == choose(state, "yes")
    state = choose(restored, "yes")
    assert state.pending is not None and state.pending.prompt == "reaction"
    assert choose(state_from_json(state_to_json(state)), "yes") == choose(state, "yes")
