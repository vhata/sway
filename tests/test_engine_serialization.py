"""Save compatibility, malformed data, and interrupted private decisions."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from sway.engine import (
    Card,
    Command,
    GameConfig,
    InvalidSnapshot,
    advance,
    new_game,
    state_from_json,
    state_to_json,
)
from sway.engine.models import Effect, Option


@pytest.mark.parametrize(
    "snapshot",
    [
        "not JSON",
        "[]",
        "null",
        "{}",
        '{"version":2,"state":{}}',
        '{"version":true,"state":{}}',
        '{"version":1,"state":[]}',
        '{"version":1,"state":{}}',
    ],
)
def test_unsupported_or_malformed_snapshot_is_rejected(snapshot: str) -> None:
    with pytest.raises(InvalidSnapshot):
        state_from_json(snapshot)


@pytest.mark.parametrize(
    "old,new",
    [
        ('"hand":[', '"hand":null,"unused":['),
        ('"name":"Player 1"', '"name":17'),
        ('"silver_played":false', '"silver_played":1'),
        ('"definition":"treasure1"', '"definition":"unknown"'),
        ('"kind":"menu"', '"kind":"alien"'),
        ('"phase":"buy"', '"phase":"sleep"'),
        ('"player_count":2', '"player_count":3'),
        ('"curse":10', '"curse":-1'),
        ('"coins":0', '"coins":-1'),
        ('"minimum":1', '"minimum":-1'),
    ],
)
def test_corrupted_typed_fields_fail_clearly(old: str, new: str) -> None:
    snapshot = state_to_json(new_game(GameConfig(), 8))
    assert old in snapshot
    with pytest.raises(InvalidSnapshot):
        state_from_json(snapshot.replace(old, new))


def test_duplicate_cards_and_inconsistent_decisions_rejected() -> None:
    state = new_game(GameConfig(), 0)
    state.players[0].hand.append(state.players[0].deck[0])
    with pytest.raises(InvalidSnapshot, match="more than one zone"):
        state_from_json(state_to_json(state))
    state.players[0].hand.pop()
    assert state.pending is not None
    state.pending = replace(state.pending, options=(Option("same"), Option("same")))
    with pytest.raises(InvalidSnapshot, match="Duplicate"):
        state_from_json(state_to_json(state))
    state.pending = None
    with pytest.raises(InvalidSnapshot, match="continuation"):
        state_from_json(state_to_json(state))


def test_finished_snapshot_cannot_contain_pending_work() -> None:
    state = new_game(GameConfig(), 0)
    state.phase = "finished"
    with pytest.raises(InvalidSnapshot, match="unresolved"):
        state_from_json(state_to_json(state))
    state.pending = None
    state.pending_effect = None
    state.effects = [Effect("resolve", 0, card_id="k24")]
    with pytest.raises(InvalidSnapshot, match="unresolved"):
        state_from_json(state_to_json(state))
    state.effects = []
    state.scores = (3, 3)
    state.winners = (0, 1)
    assert state_from_json(state_to_json(state)) == state


@pytest.mark.parametrize(
    "field",
    [
        "pending_owner",
        "continuation_owner",
        "stack_owner",
        "stack_kind",
        "continuation_kind",
        "mismatched_owner",
    ],
)
def test_invalid_continuation_ownership_and_kind_fail_before_advance(field: str) -> None:
    state = new_game(GameConfig(), 7)
    assert state.pending is not None and state.pending_effect is not None
    if field == "pending_owner":
        state.pending = replace(state.pending, player=999)
    elif field == "continuation_owner":
        state.pending_effect = replace(state.pending_effect, player=999)
    elif field == "stack_owner":
        state.effects.append(Effect("library", 999))
    elif field == "stack_kind":
        state.effects.append(Effect("unknown", state.active_player))
    elif field == "continuation_kind":
        state.pending_effect = replace(state.pending_effect, kind="unknown")
    else:
        state.pending_effect = replace(state.pending_effect, player=(state.active_player + 1) % 2)
    with pytest.raises(InvalidSnapshot):
        state_from_json(state_to_json(state))


@pytest.mark.parametrize(
    "field",
    [
        "card_sequence",
        "decision_sequence",
        "card_identifier",
        "pending_missing",
        "bad_config",
        "bad_supply",
        "bad_options",
        "bad_bounds",
        "bad_menu",
        "bad_event",
        "bad_random",
        "bad_turns",
        "bad_results",
    ],
)
def test_corrupt_save_cannot_reuse_identifiers_or_restore_an_unplayable_state(field: str) -> None:
    state = new_game(GameConfig(), 7)
    assert state.pending is not None
    if field == "card_sequence":
        state.next_instance_id = 1
    elif field == "decision_sequence":
        state.next_decision_id = 1
    elif field == "card_identifier":
        old = state.players[0].deck[0]
        state.players[0].deck[0] = Card("not-generated", old.definition)
    elif field == "pending_missing":
        state.pending = state.pending_effect = None
    elif field == "bad_config":
        state.config = replace(state.config, kingdom=("k01",) * 10)
    elif field == "bad_supply":
        state.supply["k01"] = 1
    elif field == "bad_options":
        state.pending = replace(state.pending, options=(Option("missing", "treasure1", "missing"),))
    elif field == "bad_bounds":
        state.pending = replace(state.pending, minimum=0)
    elif field == "bad_menu":
        state.phase = "action"
    elif field == "bad_event":
        state.events[0] = replace(state.events[0], audience=999)
    elif field == "bad_random":
        state.rng_state = -1
    elif field == "bad_turns":
        state.players[0].turns = -1
    else:
        state.phase = "finished"
        state.pending = state.pending_effect = None
    with pytest.raises(InvalidSnapshot):
        state_from_json(state_to_json(state))


def test_save_is_plain_json_and_preserves_names_without_html_processing() -> None:
    state = new_game(GameConfig(player_names=("<script>name</script>", "Δοκιμή")), -12)
    snapshot = state_to_json(state)
    assert json.loads(snapshot)["version"] == 1
    assert state_from_json(snapshot) == state
    assert state.pending is not None
    command = Command(state.pending.id, state.revision, ("end-turn",))
    uninterrupted = advance(state, command)
    resumed = advance(state_from_json(snapshot), command)
    assert uninterrupted == resumed
