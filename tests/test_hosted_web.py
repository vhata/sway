"""Separate browser identities exercise the hosted HTTP authorization boundary."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Client, Response

from sway.hosting.config import HostedConfig
from sway.hosting.identity import IdentityService
from sway.hosting.service import HostedService
from sway.hosting.storage import HostedStore
from sway.hosting.web import COOKIE, create_app

ORIGIN = "https://sway.test"


def make_client(app: FastAPI) -> Client:
    return TestClient(app, base_url=ORIGIN)


def csrf(response: Response) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', response.text)
    assert match is not None, response.text
    return match[1]


def post(
    client: Client, path: str, data: dict[str, str], *, source: Response | None = None
) -> Response:
    current = source if source is not None else client.get("/account")
    return client.post(path, data={"csrf": csrf(current), **data}, headers={"Origin": ORIGIN})


def player(client: Client, name: str) -> str:
    result = post(client, "/identity", {"display_name": name})
    assert result.status_code == 200, result.text
    recovery = re.search(r'<code id="recovery-code">([^<]+)</code>', result.text)
    assert recovery is not None
    return recovery[1]


@pytest.fixture
def config(tmp_path: Path) -> HostedConfig:
    return HostedConfig(ORIGIN, tmp_path / "hosted", local_data_dir=tmp_path / "local")


def test_anonymous_get_does_not_create_player_and_cookies_are_private(config: HostedConfig) -> None:
    client: Client = make_client(create_app(config))
    response = client.get("/")
    assert response.status_code == 200
    assert all(
        value in response.headers["set-cookie"]
        for value in ("Secure", "HttpOnly", "SameSite=lax", "Path=/")
    )
    assert "Domain=" not in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "same-origin"
    with HostedStore(config.database_path).transaction() as conn:
        assert conn.execute("SELECT count(*) FROM principals").fetchone()[0] == 0
    player(client, "Alice")
    with HostedStore(config.database_path).transaction() as conn:
        assert conn.execute("SELECT count(*) FROM principals").fetchone()[0] == 1


@pytest.mark.parametrize("count", (2, 3, 4))
def test_invited_humans_ready_start_private_decisions_and_retry(
    config: HostedConfig, count: int
) -> None:
    app = create_app(config)
    clients: list[Client] = [make_client(app) for _ in range(count)]
    host = clients[0]
    player(host, "Alice")
    created = post(host, "/games", {"players": str(count)})
    assert created.status_code == 200, created.text
    path = created.url.path
    for seat, guest in enumerate(clients[1:], 1):
        invited = post(host, f"{path}/invite", {"seat": str(seat)})
        link = re.search(r'id="invitation-link"[^>]*value="([^"]+)"', invited.text)
        assert link is not None, invited.text
        join_url, secret = link[1].split("#")
        preview = guest.get(join_url)
        assert "Alice" not in preview.text
        assert (
            HostedService(HostedStore(config.database_path))
            .view(host.cookies[COOKIE], path.split("/")[-1])
            .seats[seat]
            .occupied
            is False
        )
        joined = post(
            guest, join_url, {"secret": secret, "display_name": f"Guest {seat}"}, source=preview
        )
        assert joined.status_code == 200, joined.text
        assert "recovery-code" in joined.text
    service = HostedService(HostedStore(config.database_path))
    game_id = path.split("/")[-1]
    early = post(
        host,
        f"{path}/start",
        {"lobby_revision": str(service.view(host.cookies[COOKIE], game_id).lobby_revision)},
    )
    assert early.status_code == 409
    for client in clients:
        table = service.view(client.cookies[COOKIE], game_id)
        ready = post(
            client, f"{path}/ready", {"lobby_revision": str(table.lobby_revision), "ready": "true"}
        )
        assert ready.status_code == 200, ready.text
    table = service.view(host.cookies[COOKIE], game_id)
    started = post(host, f"{path}/start", {"lobby_revision": str(table.lobby_revision)})
    assert started.status_code == 200, started.text
    assert "Game seed" not in started.text
    initial = service.view(host.cookies[COOKIE], game_id)
    assert initial.pending_player is not None
    actor = clients[initial.pending_player]
    outsiders = [client for client in clients if client is not actor]
    for guest in outsiders:
        waiting = guest.get(path)
        assert "Waiting for " in waiting.text
        assert 'id="decision-form"' not in waiting.text
        assert 'id="bot-progress"' not in waiting.text
    current = service.view(actor.cookies[COOKIE], game_id)
    assert current.view is not None and current.view.pending is not None
    decision = current.view.pending
    values = {
        "request_id": "browser-test-request",
        "decision": decision.id,
        "revision": str(current.revision),
        "choices": decision.options[-1].id,
    }
    forbidden = post(outsiders[0], f"{path}/decisions", values)
    assert forbidden.status_code == 409
    accepted = post(actor, f"{path}/decisions", values)
    assert accepted.status_code == 200, accepted.text
    revision = service.view(host.cookies[COOKIE], game_id).revision
    retried = post(actor, f"{path}/decisions", values)
    assert retried.status_code == 200
    assert service.view(host.cookies[COOKIE], game_id).revision == revision


def test_membership_applies_to_pages_updates_and_mutations(config: HostedConfig) -> None:
    app = create_app(config)
    host: Client = make_client(app)
    stranger: Client = make_client(app)
    player(host, "Host")
    player(stranger, "Stranger")
    created = post(host, "/games", {"controller1": "economy"})
    path = created.url.path
    assert path not in stranger.get("/").text
    for suffix in ("", "/updates"):
        actual = stranger.get(path + suffix)
        unknown = stranger.get("/games/unknown" + suffix)
        assert actual.status_code == unknown.status_code == 404
        assert actual.text == unknown.text
    for action in ("cancel", "retry", "invite", "theme", "decisions"):
        result = post(
            stranger,
            f"{path}/{action}",
            {
                "seat": "1",
                "theme": "orbital",
                "preference_version": "0",
                "request_id": "forbidden",
                "decision": "anything",
                "revision": "0",
            },
        )
        assert result.status_code == 404, (action, result.text)


def test_csrf_origin_host_body_and_rate_limits(config: HostedConfig) -> None:
    client: Client = make_client(create_app(config))
    first = client.get("/")
    for headers in (
        {},
        {"Origin": "https://evil.test"},
        {"Origin": ORIGIN, "Sec-Fetch-Site": "cross-site"},
    ):
        assert (
            client.post(
                "/identity", data={"csrf": csrf(first), "display_name": "Alice"}, headers=headers
            ).status_code
            == 403
        )
    bad_csrf = client.post(
        "/identity", data={"csrf": "wrong", "display_name": "Alice"}, headers={"Origin": ORIGIN}
    )
    assert bad_csrf.status_code == 403
    assert (
        client.get("/", headers={"Host": "evil.test", "X-Forwarded-Host": "sway.test"}).status_code
        == 400
    )
    oversized = client.post(
        "/games",
        content="x=" + "a" * (config.max_request_bytes + 1),
        headers={"Origin": ORIGIN, "Content-Type": "application/x-www-form-urlencoded"},
    )
    assert oversized.status_code == 413
    for _ in range(config.credential_requests_per_minute):
        client.get("/join/fake")
    assert client.get("/join/fake").status_code == 429


def test_recovery_revokes_old_browser_and_theme_does_not_advance_game(config: HostedConfig) -> None:
    app = create_app(config)
    old: Client = make_client(app)
    recovered: Client = make_client(app)
    code = player(old, "Alice")
    created = post(old, "/games", {"controller1": "economy"})
    path = created.url.path
    restored = post(recovered, "/recover", {"recovery_code": code})
    assert restored.status_code == 200
    assert old.get(path).status_code == 401
    assert old.get(f"{path}/updates").status_code == 401
    assert path in recovered.get("/").text
    theme = post(recovered, f"{path}/theme", {"theme": "orbital", "preference_version": "0"})
    assert theme.status_code == 200
    table = HostedService(HostedStore(config.database_path)).view(
        recovered.cookies[COOKIE], path.split("/")[-1]
    )
    assert table.revision == 0
    assert table.preference_version == 1
    assert table.theme_id == "orbital"


def test_lost_access_poll_and_unchanged_poll_do_not_mutate(config: HostedConfig) -> None:
    client: Client = make_client(create_app(config))
    player(client, "Alice")
    created = post(client, "/games", {"controller1": "economy"})
    path = created.url.path
    store = HostedStore(config.database_path)
    table = HostedService(store).view(client.cookies[COOKIE], path.split("/")[-1])
    unchanged = client.get(
        f"{path}/updates",
        params={
            "revision": table.revision,
            "lobby_revision": table.lobby_revision,
            "preference_version": table.preference_version,
        },
    )
    assert unchanged.status_code == 204
    IdentityService(store).revoke_all(client.cookies[COOKIE])
    assert client.get(f"{path}/updates").status_code == 401
    assert client.get(path).status_code == 401


def test_failed_guest_join_rolls_back_identity_and_preserves_anonymous_session(
    config: HostedConfig,
) -> None:
    client: Client = make_client(create_app(config))
    preview = client.get("/join/missing")
    bearer = client.cookies[COOKIE]
    result = post(
        client, "/join/missing", {"secret": "wrong", "display_name": "Guest"}, source=preview
    )
    assert result.status_code == 404
    store = HostedStore(config.database_path)
    assert IdentityService(store).authenticate(bearer).principal_id is None
    with store.transaction() as conn:
        assert conn.execute("SELECT count(*) FROM principals").fetchone()[0] == 0


def test_stale_tab_csrf_does_not_sign_out_current_player(config: HostedConfig) -> None:
    client = make_client(create_app(config))
    old_form = client.get("/")
    player(client, "Alice")
    bearer = client.cookies[COOKIE]
    stale = post(client, "/games", {}, source=old_form)
    assert stale.status_code == 403
    assert client.cookies[COOKIE] == bearer
    assert "Set a private table" in client.get("/").text


def test_invalid_manual_setup_keeps_players_opponents_and_chosen_cards(
    config: HostedConfig,
) -> None:
    client = make_client(create_app(config))
    player(client, "Alice")
    response = post(
        client,
        "/games",
        {
            "players": "4",
            "controller1": "attack",
            "controller2": "human",
            "controller3": "engine",
            "supply": "manual",
            "kingdom": "k01",
        },
    )
    assert response.status_code == 422
    assert "Choose ten different supply cards" in response.text
    assert '<option value="4" selected>' in response.text
    assert '<option value="attack" selected>' in response.text
    assert '<option value="engine" selected>' in response.text
    assert '<option value="manual" selected>' in response.text
    assert 'name="kingdom" value="k01" checked' in response.text
    assert (
        HostedService(HostedStore(config.database_path)).list_tables(client.cookies[COOKIE]) == ()
    )


def test_public_assets_do_not_consume_private_page_rate_budget(config: HostedConfig) -> None:
    client = make_client(create_app(config))
    for _ in range(310):
        assert client.get("/static/hosted.js").status_code == 200
    assert client.get("/").status_code == 200
    for _ in range(300):
        client.get("/account")
    assert client.get("/account").status_code == 429
    assert client.get("/static/hosted.js").status_code == 200
