"""Bot behaviour, legal generic choices and replayable private strategy state."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from random import Random

import pytest

from sway.bots import STRATEGIES, BotState, choose
from sway.engine import (
    KINGDOM_IDS,
    Card,
    Decision,
    GameConfig,
    Option,
    PlayerView,
    advance,
    new_game,
    state_from_json,
    state_to_json,
    view_for,
)
from sway.simulate import simulate_game


def visible(decision: Decision, *, actions: int = 1) -> PlayerView:
    state = new_game(GameConfig(), 42)
    view = view_for(state, decision.player)
    return replace(
        view,
        player=decision.player,
        active_player=decision.player,
        pending=decision,
        actions=actions,
    )


def choice(prompt: str, card_ids: tuple[str, ...], minimum: int = 0, maximum: int = 1) -> Decision:
    return Decision(
        "test",
        0,
        "select",
        prompt,
        tuple(Option(str(index), card, str(index)) for index, card in enumerate(card_ids)),
        minimum,
        maximum,
    )


@pytest.mark.parametrize("profile", STRATEGIES)
@pytest.mark.parametrize("players", (2, 3, 4))
def test_profiles_complete_real_games(profile: str, players: int) -> None:
    kingdom = tuple(sorted(Random(players + 17).sample(KINGDOM_IDS, 10)))
    result = simulate_game(GameConfig(players, kingdom), 12 + players, (profile,) * players)
    assert result.finished, result
    assert result.decisions < 4000
    assert len(result.scores) == players
    assert result.winners


def test_profile_purchase_preferences_are_distinct() -> None:
    decision = Decision(
        "buy",
        0,
        "menu",
        "buy",
        (
            Option("treasure3", "treasure3"),
            Option("k10", "k10"),
            Option("k25", "k25"),
            Option("end-turn"),
        ),
        1,
        1,
    )
    view = visible(decision)
    selections = {
        profile: choose(view, decision, BotState(profile, 7)).command.selections
        for profile in STRATEGIES
    }
    assert selections == {"economy": ("treasure3",), "engine": ("k10",), "attack": ("k25",)}


def test_play_treasures_before_buying_and_never_buy_free_junk() -> None:
    decision = Decision(
        "buy",
        0,
        "menu",
        "buy",
        (
            Option("play-treasures"),
            Option("treasure1", "treasure1"),
            Option("curse", "curse"),
            Option("end-turn"),
        ),
        1,
        1,
    )
    assert choose(visible(decision), decision, BotState("economy", 0)).command.selections == (
        "play-treasures",
    )
    decision = replace(decision, options=decision.options[1:])
    assert choose(visible(decision), decision, BotState("economy", 0)).command.selections == (
        "end-turn",
    )


def test_chapel_trashes_junk_but_preserves_a_buying_economy() -> None:
    decision = choice(
        "chapel", ("curse", "victory1", "treasure1", "treasure1", "treasure1", "treasure1"), 0, 4
    )
    result = choose(visible(decision), decision, BotState("engine", 3))
    assert {"0", "1"} <= set(result.command.selections)
    assert len(result.command.selections) == 4  # At most two of the seven known coppers.
    assert result.state.decisions == 1


def test_discard_loses_victory_before_money() -> None:
    decision = choice("militia", ("treasure3", "victory3", "curse", "treasure1"), 2, 2)
    assert set(choose(visible(decision), decision, BotState("economy", 6)).command.selections) == {
        "1",
        "2",
    }


def test_action_capacity_before_terminal_draw() -> None:
    decision = replace(choice("action", ("k21", "k24"), 1, 1), kind="menu")
    view = replace(visible(decision), hand=(Card("0", "k21"), Card("1", "k24")))
    assert choose(view, decision, BotState("engine", 9)).command.selections == ("1",)


@pytest.mark.parametrize("prompt", ("reaction", "vassal", "library"))
@pytest.mark.parametrize("actions", (0, 1))
def test_yes_no_decisions(prompt: str, actions: int) -> None:
    decision = Decision("yes-no", 0, "yes_no", prompt, (Option("yes"), Option("no")), 1, 1)
    result = choose(visible(decision, actions=actions), decision, BotState("attack", 0))
    expected = "no" if prompt == "library" and actions == 0 else "yes"
    assert result.command.selections == (expected,)


@pytest.mark.parametrize(
    "prompt,cards,minimum,maximum",
    (
        ("cellar", ("curse", "treasure3", "victory2"), 0, 3),
        ("harbinger", ("treasure2", "victory1"), 0, 1),
        ("mine", ("treasure1", "treasure2", "treasure3"), 0, 1),
        ("moneylender", ("treasure1",), 0, 1),
        ("poacher", ("victory2", "treasure1", "treasure3"), 2, 2),
        ("remodel", ("treasure3", "victory1"), 1, 1),
        ("throne", ("k21", "k24"), 0, 1),
        ("topdeck", ("treasure3", "victory1"), 1, 1),
        ("bandit", ("treasure2", "treasure3"), 1, 1),
        ("bureaucrat", ("victory1", "victory3"), 1, 1),
        ("sentry_trash", ("treasure1", "curse"), 0, 2),
        ("sentry_discard", ("victory1", "treasure3"), 0, 2),
    ),
)
@pytest.mark.parametrize("profile", STRATEGIES)
def test_base_prompts_produce_legal_choices(
    prompt: str, cards: tuple[str, ...], minimum: int, maximum: int, profile: str
) -> None:
    decision = choice(prompt, cards, minimum, maximum)
    result = choose(visible(decision), decision, BotState(profile, 33))
    selected = result.command.selections
    assert minimum <= len(selected) <= maximum
    assert len(set(selected)) == len(selected)
    assert set(selected) <= {option.id for option in decision.options}


def test_order_places_next_useful_draw_first() -> None:
    decision = replace(
        choice("sentry_order", ("treasure1", "treasure3"), 2, 2), kind="order", ordered=True
    )
    assert choose(visible(decision), decision, BotState("economy", 7)).command.selections == (
        "1",
        "0",
    )


@pytest.mark.parametrize("prompt", ("gain", "gain_hand"))
def test_required_gain_always_selects_even_when_no_good_card_remains(prompt: str) -> None:
    decision = Decision("gain", 0, "supply", prompt, (Option("curse", "curse"),), 1, 1)
    assert choose(visible(decision), decision, BotState("economy", 7)).command.selections == (
        "curse",
    )


def test_private_random_state_and_snapshot_resume_reproduce_commands() -> None:
    game = new_game(GameConfig(), 190)
    bots = [BotState("engine", 19), BotState("attack", 29)]
    for _ in range(35):
        assert game.pending is not None
        decision = game.pending
        view = view_for(game, decision.player)
        before = deepcopy(view)
        bot = bots[decision.player]
        result = choose(view, decision, bot)
        restored = state_from_json(state_to_json(game))
        assert restored.pending is not None
        restored_choice = choose(
            view_for(restored, decision.player), restored.pending, replace(bot)
        )
        assert result == restored_choice
        assert before == view
        assert bot.decisions + 1 == result.state.decisions
        assert advance(game, result.command) == advance(restored, restored_choice.command)
        bots[decision.player] = result.state
        game = advance(game, result.command).state


def test_bot_rejects_other_players_and_unsupported_saved_versions() -> None:
    decision = choice("harbinger", (), 0, 0)
    view = visible(decision)
    for bot in (
        BotState("missing", 1),
        BotState("economy", 1, version=2),
        BotState("economy", 1, decisions=-1),
    ):
        with pytest.raises(ValueError, match="Unsupported"):
            choose(view, decision, bot)
    with pytest.raises(ValueError, match="visible decision"):
        choose(replace(view, player=1), decision, BotState("engine", 2))
