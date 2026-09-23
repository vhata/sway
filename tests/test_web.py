"""HTTP contract tests use the real rules engine and transactional storage."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Client

from sway.engine.catalog import CATALOG, OFFICIAL_NAMES
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
            "theme": "common-ground",
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


def test_retained_setup_text_is_escaped_and_not_accepted_as_valid(client: Client) -> None:
    token = csrf(client)
    payload = '"><script>alert("setup")</script>'
    response = client.post(
        "/games",
        data={
            "csrf": token,
            "players": "4",
            "seed": payload,
            "theme": "orbital",
            "supply": "manual",
        },
    )
    assert response.status_code == 422
    assert "<script>alert" not in response.text
    assert "&lt;script&gt;" in response.text
    assert 'value="4" selected' in response.text
    assert 'value="orbital" selected' in response.text


def test_invalid_theme_preserves_active_pack(client: Client, tmp_path: Path) -> None:
    token = csrf(client)
    identifier = create_game(client, token)
    response = client.post(
        f"/games/{identifier}/theme", data={"csrf": token, "theme": "../../escape"}
    )
    assert response.status_code == 422
    service = GameService(SQLiteStore(tmp_path / "games.sqlite3"))
    assert service.load(identifier).theme_id == "common-ground"


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
    (packs / "common-ground.json").write_text("invalid pack")
    monkeypatch.setattr(theme_module, "THEME_ROOT", packs)
    restarted = make_client(tmp_path)
    response = restarted.get(f"/games/{identifier}")
    assert response.status_code == 200
    assert "showing Orbital Commons" in response.text
    assert "Your game is unchanged" in response.text
    assert restarted.get("/").status_code == 200
    assert service.load(identifier) == original


@pytest.mark.parametrize("flag", [None, "0", "true", "1"])
def test_developer_terminology_is_opt_in_and_survives_updates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flag: str | None
) -> None:
    if flag is None:
        monkeypatch.delenv("SWAY_DEV_TERMINOLOGY", raising=False)
    else:
        monkeypatch.setenv("SWAY_DEV_TERMINOLOGY", flag)
    enabled = flag == "1"
    client = make_client(tmp_path)
    token = csrf(client)
    setup = client.get("/").text
    assert ("Original: Village" in setup) is enabled
    invalid = client.post("/games", data={"csrf": token, "players": "5"})
    assert invalid.status_code == 422
    assert ("Original: Village" in invalid.text) is enabled
    identifier = create_game(client, token)
    service = GameService(SQLiteStore(tmp_path / "games.sqlite3"))
    before = service.load(identifier)
    for theme in ("common-ground", "orbital"):
        changed = client.post(
            f"/games/{identifier}/theme",
            data={"csrf": token, "theme": theme},
            headers={"HX-Request": "true"},
        )
        assert changed.status_code == 200
        assert "<html" not in changed.text
        for response in (changed, client.get(f"/games/{identifier}")):
            assert ("Original: Copper" in response.text) is enabled
            assert ("Original: Village" in response.text) is enabled
            if not enabled:
                assert 'class="original-name"' not in response.text
                for name in OFFICIAL_NAMES.values():
                    assert f"Original: {name}" not in response.text
        assert service.load(identifier).state == before.state
        assert service.load(identifier).revision == before.revision

    # A real human decision and bounded bot advancement both return the same mode.
    view = service.view(identifier)
    for _ in range(20):
        if view.pending:
            break
        advanced = client.post(
            f"/games/{identifier}/advance",
            data={"csrf": token, "revision": str(view.revision)},
            headers={"HX-Request": "true"},
        )
        assert advanced.status_code == 200
        assert ("Original: Copper" in advanced.text) is enabled
        view = service.view(identifier)
    assert view.pending is not None
    selected = view.pending.options[-1].id
    decision = client.post(
        f"/games/{identifier}/decisions",
        data={
            "csrf": token,
            "revision": str(view.revision),
            "decision": view.pending.id,
            "choices": selected,
        },
        headers={"HX-Request": "true"},
    )
    assert decision.status_code == 200
    assert ("Original: Copper" in decision.text) is enabled
    assert service.load(identifier).revision == view.revision + 1


def test_original_name_mapping_matches_catalog_and_developer_reference() -> None:
    reference = Path(__file__).resolve().parents[1] / "docs/TERMINOLOGY.md"
    documented = {
        card_id: name.strip()
        for card_id, name in re.findall(r"\| `([^`]+)` \| ([^|]+) \|", reference.read_text())
        if card_id in CATALOG
    }
    assert set(OFFICIAL_NAMES) == set(CATALOG)
    assert documented == OFFICIAL_NAMES


@pytest.mark.parametrize("humans", [frozenset({1}), frozenset({0, 1})])
def test_local_browser_rejects_other_human_arrangements_without_mutation(
    client: Client, tmp_path: Path, humans: frozenset[int]
) -> None:
    from sway.engine import GameConfig

    token = csrf(client)
    service = GameService(SQLiteStore(tmp_path / "games.sqlite3"))
    record = service.create(
        GameConfig(), 4, ("economy",) if len(humans) == 1 else (), human_seats=humans
    )
    before = service.store.load(record.game_id)
    assert record.state.pending is not None
    form = {
        "csrf": token,
        "revision": "0",
        "decision": record.state.pending.id,
        "choices": record.state.pending.options[0].id,
        "theme": "orbital",
        "player": "1",
    }
    assert client.get("/").status_code == 200
    for headers in ({}, {"HX-Request": "true"}):
        responses = [client.get(f"/games/{record.game_id}", headers=headers)]
        responses.extend(
            client.post(f"/games/{record.game_id}/{route}", data=form, headers=headers)
            for route in ("decisions", "advance", "theme")
        )
        for response in responses:
            assert response.status_code == 422
            assert "player arrangement" in response.text
            assert "preserved" in response.text
            assert 'id="bot-progress"' not in response.text
            assert 'id="decision-form"' not in response.text
        assert service.store.load(record.game_id) == before
        assert service.store.history(record.game_id) == []
