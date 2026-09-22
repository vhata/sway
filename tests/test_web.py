"""HTTP contract tests use the real rules engine and transactional storage."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Client

from sway.service import GameService
from sway.storage import SQLiteStore
from sway.web import create_app


def csrf(client: Client) -> str:
    response = client.get("/")
    assert response.status_code == 200
    match = re.search(r'name="csrf" value="([^"]+)"', response.text)
    assert match is not None
    return match.group(1)


def create_game(client: Client, token: str, **fields: str) -> str:
    response = client.post(
        "/games",
        data={
            "csrf": token,
            "players": "2",
            "seed": "13",
            "strategy1": "economy",
            "theme": "neutral",
            "supply": "starter",
            **fields,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return response.headers["location"].rsplit("/", 1)[1]


def make_client(path: Path) -> Client:
    return TestClient(create_app(path))


@pytest.fixture
def client(tmp_path: Path) -> Client:
    return make_client(tmp_path)


def test_setup_resume_and_theme_change_preserve_state(client: Client, tmp_path: Path) -> None:
    token = csrf(client)
    identifier = create_game(client, token)
    service = GameService(SQLiteStore(tmp_path / "games.sqlite3"))
    before = service.load(identifier)
    response = client.get(f"/games/{identifier}")
    assert response.status_code == 200
    assert "Common Ground" in response.text
    changed = client.post(
        f"/games/{identifier}/theme",
        data={"csrf": token, "theme": "orbital"},
        headers={"HX-Request": "true"},
    )
    assert changed.status_code == 200
    assert "Orbital Commons" in changed.text
    assert "<!doctype" not in changed.text.lower()
    after = service.load(identifier)
    assert after.state == before.state
    assert after.revision == before.revision
    restarted = make_client(tmp_path)
    assert "Orbital Commons" in restarted.get(f"/games/{identifier}").text
    assert identifier in restarted.get("/").text


def test_csrf_origin_and_host_checks(client: Client) -> None:
    token = csrf(client)
    assert client.post("/games", data={"players": "2"}).status_code == 403
    assert (
        client.post(
            "/games", data={"csrf": token}, headers={"Origin": "https://untrusted.invalid"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/games", data={"csrf": token}, headers={"Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 403
    )
    assert client.get("/", headers={"Host": "untrusted.invalid"}).status_code == 400


def test_invalid_setup_and_missing_game(client: Client) -> None:
    token = csrf(client)
    for fields in [
        {"players": "5"},
        {"seed": "-1"},
        {"supply": "manual"},
        {"theme": "missing"},
        {"strategy1": "missing"},
    ]:
        response = client.post("/games", data={"csrf": token, "players": "2", **fields})
        assert response.status_code == 422
    assert client.get("/games/missing").status_code == 404


def test_invalid_theme_preserves_active_pack(client: Client, tmp_path: Path) -> None:
    token = csrf(client)
    identifier = create_game(client, token)
    response = client.post(
        f"/games/{identifier}/theme", data={"csrf": token, "theme": "../../escape"}
    )
    assert response.status_code == 422
    service = GameService(SQLiteStore(tmp_path / "games.sqlite3"))
    assert service.load(identifier).theme_id == "neutral"


def test_decision_rejects_stale_revision_and_advances_only_once(
    client: Client, tmp_path: Path
) -> None:
    token = csrf(client)
    identifier = create_game(client, token)
    service = GameService(SQLiteStore(tmp_path / "games.sqlite3"))
    for _ in range(100):
        view = service.view(identifier)
        if view.pending is not None:
            break
        response = client.post(
            f"/games/{identifier}/advance", data={"csrf": token, "revision": str(view.revision)}
        )
        assert response.status_code == 200
    view = service.view(identifier)
    assert view.pending is not None
    choice = next(
        (option.id for option in view.pending.options if option.id in {"end-actions", "end-turn"}),
        view.pending.options[0].id,
    )
    form = {
        "csrf": token,
        "revision": str(view.revision),
        "decision": view.pending.id,
        "choices": choice,
    }
    accepted = client.post(f"/games/{identifier}/decisions", data=form)
    assert accepted.status_code == 200, accepted.text
    revision = service.load(identifier).revision
    duplicate = client.post(f"/games/{identifier}/decisions", data=form)
    assert duplicate.status_code in {200, 409}
    assert service.load(identifier).revision == revision
    stale = client.post(f"/games/{identifier}/decisions", data={**form, "revision": "-1"})
    assert stale.status_code == 409
    assert service.load(identifier).revision == revision


def test_incompatible_save_does_not_block_healthy_tables(client: Client, tmp_path: Path) -> None:
    token = csrf(client)
    broken = create_game(client, token)
    healthy = create_game(client, token, seed="99")
    store = SQLiteStore(tmp_path / "games.sqlite3")
    saved = store.load(broken)
    store.commit(broken, saved.revision, "unsupported", '{"schema":999}', "{}", "[]")
    assert client.get("/").status_code == 200
    assert client.get(f"/games/{healthy}").status_code == 200
    unavailable = client.get(f"/games/{broken}")
    assert unavailable.status_code == 422
    assert "preserved" in unavailable.text
    assert store.load(broken).snapshot == '{"schema":999}'


def test_unavailable_saved_theme_falls_back_without_changing_save(
    client: Client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sway.presentation import themes as theme_module

    token = csrf(client)
    identifier = create_game(client, token)
    service = GameService(SQLiteStore(tmp_path / "games.sqlite3"))
    original = service.load(identifier)
    packs = tmp_path / "packs"
    packs.mkdir()
    (packs / "orbital.json").write_text((theme_module.THEME_ROOT / "orbital.json").read_text())
    (packs / "neutral.json").write_text("invalid pack")
    monkeypatch.setattr(theme_module, "THEME_ROOT", packs)
    restarted = make_client(tmp_path)
    response = restarted.get(f"/games/{identifier}")
    assert response.status_code == 200
    assert "showing Orbital Commons" in response.text
    assert "Your game is unchanged" in response.text
    assert restarted.get("/").status_code == 200
    assert service.load(identifier) == original
