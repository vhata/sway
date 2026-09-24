"""The developer catalogue stays opt-in and never opens saved-game storage."""

from html import escape
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Client

from sway.engine.catalog import CATALOG, OFFICIAL_NAMES
from sway.presentation.themes import load_themes
from sway.web import create_app


def make_client(directory: Path) -> Client:
    return TestClient(create_app(directory))


@pytest.mark.parametrize("flag", [None, "0", "true", "yes", ""])
def test_reference_requires_explicit_developer_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flag: str | None
) -> None:
    if flag is None:
        monkeypatch.delenv("SWAY_DEV_TERMINOLOGY", raising=False)
    else:
        monkeypatch.setenv("SWAY_DEV_TERMINOLOGY", flag)
    directory = tmp_path / "unopened"
    with make_client(directory) as client:
        response = client.get("/developer/cards")
        assert response.status_code == 404
        assert "Original:" not in response.text
    assert not directory.exists()


@pytest.mark.parametrize("theme_id", ["common-ground", "orbital"])
def test_reference_contains_every_card_and_never_opens_saves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, theme_id: str
) -> None:
    monkeypatch.setenv("SWAY_DEV_TERMINOLOGY", "1")
    directory = tmp_path / "unopened"
    themes = load_themes(frozenset(CATALOG))
    with make_client(directory) as client:
        response = client.get("/developer/cards", params={"theme": theme_id})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.text.count("data-card-id=") == len(CATALOG)
        for card_id, card in themes[theme_id].cards.items():
            assert f'data-card-id="{card_id}"' in response.text
            assert escape(card.name) in response.text
            assert f"Original: {escape(OFFICIAL_NAMES[card_id])}" in response.text
            assert f'src="/static/{card.image}"' in response.text
        assert f'value="{theme_id}" selected' in response.text
    assert not directory.exists()


def test_reference_rejects_unknown_themes_and_defaults_to_common_ground(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SWAY_DEV_TERMINOLOGY", "1")
    directory = tmp_path / "unopened"
    with make_client(directory) as client:
        default = client.get("/developer/cards")
        assert default.status_code == 200
        assert 'value="common-ground" selected' in default.text
        for invalid in ("missing", "../../escape", "<script>", ""):
            response = client.get("/developer/cards", params={"theme": invalid})
            assert response.status_code == 422
            assert "Choose an available theme" in response.text
            assert "<script>" not in response.text
    assert not directory.exists()
