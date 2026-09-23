"""Presentation packs must be complete, safe, and independent of rules."""

import json
from dataclasses import replace
from pathlib import Path
from typing import cast
from xml.etree import ElementTree

import pytest

from sway.engine import GameConfig, new_game, view_for
from sway.engine.catalog import CATALOG, OFFICIAL_NAMES
from sway.engine.models import Decision, Option
from sway.presentation.components import BoardContext, board, card_face, choice_form, event_text
from sway.presentation.themes import STATIC_ROOT, THEME_ROOT, load_theme, load_themes


def test_every_theme_covers_catalog_and_has_original_names() -> None:
    themes = load_themes(frozenset(CATALOG))
    assert set(themes) == {"common-ground", "orbital"}
    for theme in themes.values():
        assert set(theme.cards) == set(CATALOG)
        assert len({card.name for card in theme.cards.values()}) == len(CATALOG)
        assert all(card.description and card.image_alt for card in theme.cards.values())


def test_bundled_illustrations_are_distinct_self_contained_svg_scenes() -> None:
    for theme in load_themes(frozenset(CATALOG)).values():
        assert len({card.image for card in theme.cards.values()}) == len(CATALOG)
        assert len({card.image_alt for card in theme.cards.values()}) == len(CATALOG)
        scenes: set[bytes] = set()
        for card in theme.cards.values():
            image = ElementTree.fromstring((STATIC_ROOT / card.image).read_text())
            assert image.attrib["viewBox"] == "0 0 240 160"
            description = image.find("{http://www.w3.org/2000/svg}desc")
            assert description is not None
            assert description.text == card.image_alt
            for node in image.iter():
                assert node.tag.rsplit("}", 1)[-1] not in {
                    "script",
                    "foreignObject",
                    "image",
                    "use",
                }
                assert not any(key.rsplit("}", 1)[-1].startswith("on") for key in node.attrib)
            scene = image.find("{http://www.w3.org/2000/svg}g")
            assert scene is not None
            scenes.add(ElementTree.tostring(scene))
        assert len(scenes) == len(CATALOG)


@pytest.mark.parametrize("theme_id", ["common-ground", "orbital"])
def test_developer_hints_supplement_every_themed_card(theme_id: str) -> None:
    theme = load_themes(frozenset(CATALOG))[theme_id]
    for card_id, official in OFFICIAL_NAMES.items():
        normal = str(card_face(card_id, theme))
        developer = str(card_face(card_id, theme, developer_terminology=True))
        hint = f'<small class="original-name">Original: {official}</small>'
        assert hint not in normal
        assert hint in developer
        themed_title = f"<strong>{theme.cards[card_id].name}</strong>"
        assert (
            str.replace(
                developer, f'<div class="card-title">{themed_title}{hint}</div>', themed_title
            )
            == normal
        )


@pytest.mark.parametrize("theme_id", ["common-ground", "orbital"])
@pytest.mark.parametrize("ordering", ["none", "subset", "full"])
def test_original_names_remain_in_card_and_ordered_choices(theme_id: str, ordering: str) -> None:
    themes = load_themes(frozenset(CATALOG))
    ctx = BoardContext(
        "game", "token", themes[theme_id], tuple(themes.values()), developer_terminology=True
    )
    view = view_for(new_game(GameConfig(), 13), 0)
    options = (Option("village", "k24"), Option("smithy", "k21"))
    decision = Decision(
        "decision",
        0,
        "order" if ordering == "full" else "select",
        "discard",
        options,
        2 if ordering == "full" else 0,
        2,
        ordering != "none",
    )
    rendered = str(choice_form(decision, view, ctx))
    for option in options:
        assert option.card_id is not None
        assert f"Original: {OFFICIAL_NAMES[option.card_id]}" in rendered
        assert themes[theme_id].cards[option.card_id].name in rendered
    normal = str(choice_form(decision, view, replace(ctx, developer_terminology=False)))
    assert "Original:" not in normal


def test_invalid_pack_coverage_and_asset_escape_are_rejected(tmp_path: Path) -> None:
    source = (THEME_ROOT / "common-ground.json").read_text()
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
    payload = cast(dict[str, object], json.loads((THEME_ROOT / "common-ground.json").read_text()))
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
    ctx = BoardContext("game", "token", themes["common-ground"], tuple(themes.values()))
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
    ctx = BoardContext("game", "token", themes["common-ground"], tuple(themes.values()))
    common_ground = str(board(view, ctx))
    orbital = str(board(view, replace(ctx, theme=themes["orbital"])))
    assert "Common Ground" in common_ground
    assert "Orbital Commons" in orbital
    assert "Worldship" in orbital
    assert repr(state) == original
    for event in view.events:
        event_text(event, view, themes["common-ground"])
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


def test_public_set_aside_cards_are_rendered_with_theme_names() -> None:
    from sway.engine.models import Card, Event

    state = new_game(GameConfig(), 13)
    view = view_for(state, 0)
    set_aside = Card("public-card", "k01")
    opponent = replace(view.players[1], set_aside=(set_aside,))
    view = replace(view, players=(view.players[0], opponent))
    themes = load_themes(frozenset(CATALOG))
    theme = themes["orbital"]
    html = str(board(view, BoardContext("game", "token", theme, tuple(themes.values()))))
    assert "Set aside" in html
    assert "Fabricator" in html
    assert "Fabricator" in event_text(Event("set_aside", 1, (set_aside,)), view, theme)
