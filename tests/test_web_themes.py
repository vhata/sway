"""Presentation packs must be complete, safe, and independent of rules."""

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from sway.engine import GameConfig, new_game, view_for
from sway.engine.catalog import CATALOG
from sway.presentation.components import BoardContext, board, event_text
from sway.presentation.themes import THEME_ROOT, load_theme, load_themes


def test_every_theme_covers_catalog_and_has_original_names() -> None:
    themes = load_themes(frozenset(CATALOG))
    assert set(themes) == {"neutral", "orbital"}
    for theme in themes.values():
        assert set(theme.cards) == set(CATALOG)
        assert len({card.name for card in theme.cards.values()}) == len(CATALOG)
        assert all(card.description and card.image_alt for card in theme.cards.values())


def test_invalid_pack_coverage_and_asset_escape_are_rejected(tmp_path: Path) -> None:
    source = (THEME_ROOT / "neutral.json").read_text()
    payload = cast(dict[str, object], json.loads(source))
    cards = cast(dict[str, dict[str, object]], payload["cards"])
    del cards["k01"]
    path = tmp_path / "incomplete.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="coverage"):
        load_theme(path, frozenset(CATALOG))
    payload = cast(dict[str, object], json.loads(source))
    cards = cast(dict[str, dict[str, object]], payload["cards"])
    cards["k01"]["image"] = "../../web.py"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="outside"):
        load_theme(path, frozenset(CATALOG))


def test_malicious_style_token_is_rejected(tmp_path: Path) -> None:
    payload = cast(dict[str, object], json.loads((THEME_ROOT / "neutral.json").read_text()))
    tokens = cast(dict[str, str], payload["tokens"])
    tokens["accent"] = "red; background: url(https://example.invalid/track)"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Cannot load"):
        load_theme(path, frozenset(CATALOG))


def test_html_escapes_names_and_contains_only_the_filtered_view() -> None:
    state = new_game(GameConfig(player_names=("<script>unsafe()</script>", "Opponent")), 13)
    view = view_for(state, 0)
    themes = load_themes(frozenset(CATALOG))
    ctx = BoardContext("game", "token", themes["neutral"], tuple(themes.values()))
    rendered = str(board(view, ctx))
    assert "<script>unsafe()" not in rendered
    assert "&lt;script&gt;unsafe()&lt;/script&gt;" in rendered
    for card in state.players[1].hand + state.players[1].deck:
        assert f'"{card.id}"' not in rendered
    assert "rng_state" not in rendered
    assert "None in" not in rendered


def test_theme_switch_rerenders_history_without_changing_rules() -> None:
    state = new_game(GameConfig(), 13)
    view = view_for(state, 0)
    themes = load_themes(frozenset(CATALOG))
    original = repr(state)
    ctx = BoardContext("game", "token", themes["neutral"], tuple(themes.values()))
    neutral = str(board(view, ctx))
    orbital = str(board(view, replace(ctx, theme=themes["orbital"])))
    assert "Common Ground" in neutral
    assert "Orbital Commons" in orbital
    assert "Worldship" in orbital
    assert repr(state) == original
    for event in view.events:
        event_text(event, view, themes["neutral"])
        event_text(event, view, themes["orbital"])


def test_discovery_isolates_invalid_packs_and_requires_one_valid_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from sway.presentation import themes as theme_module

    (tmp_path / "orbital.json").write_text((THEME_ROOT / "orbital.json").read_text())
    (tmp_path / "broken.json").write_text('{"version":1}')
    monkeypatch.setattr(theme_module, "THEME_ROOT", tmp_path)
    loaded = load_themes(frozenset(CATALOG))
    assert set(loaded) == {"orbital"}
    assert "Skipping invalid theme broken.json" in caplog.text
    (tmp_path / "orbital.json").unlink()
    with pytest.raises(ValueError, match="At least one valid"):
        load_themes(frozenset(CATALOG))
