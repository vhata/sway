"""Real HTTPS browsers exercise private identities and serialized hosted updates."""

from __future__ import annotations

import os
import socket
import ssl
import subprocess
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs
from urllib.request import urlopen
from uuid import uuid4

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Request, Route, expect

from sway.hosting.identity import IdentityCredentials
from sway.hosting.service import HostedService, TableView
from sway.hosting.storage import HostedStore

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).resolve().parents[2]
COOKIE = "__Host-sway_session"


@dataclass(frozen=True)
class HostedServer:
    url: str
    directory: Path

    @property
    def service(self) -> HostedService:
        return HostedService(HostedStore(self.directory / "hosted.sqlite3"))


@contextmanager
def serve(directory: Path, *, port: int | None = None) -> Generator[HostedServer]:
    directory.mkdir(mode=0o700, exist_ok=True)
    key, cert = directory / "key.pem", directory / "cert.pem"
    if not key.exists():
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(key),
                "-out",
                str(cert),
                "-days",
                "1",
                "-subj",
                "/CN=127.0.0.1",
            ],
            check=True,
            capture_output=True,
        )
    if port is None:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
    url = f"https://127.0.0.1:{port}"
    environment = {
        **os.environ,
        "SWAY_HOSTED_ORIGIN": url,
        "SWAY_HOSTED_DATA_DIR": str(directory),
        "SWAY_DATA_DIR": str(directory.parent / "unused-local"),
        "SWAY_HOSTED_CREDENTIALS_PER_MINUTE": "1000",
        "SWAY_HOSTED_MUTATIONS_PER_MINUTE": "1000",
    }
    log_path = directory / "server.log"
    with (
        log_path.open("a") as log,
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "sway.hosting.web:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--ssl-keyfile",
                str(key),
                "--ssl-certfile",
                str(cert),
                "--no-proxy-headers",
            ],
            cwd=ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        ) as process,
    ):
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            for _ in range(100):
                if process.poll() is not None:
                    pytest.fail(log_path.read_text())
                try:
                    with urlopen(url, timeout=0.5, context=context) as response:
                        if response.status == 200:
                            break
                except (URLError, TimeoutError):
                    time.sleep(0.1)
            else:
                pytest.fail("Hosted HTTPS server did not become ready within ten seconds.")
            yield HostedServer(url, directory)
        finally:
            process.terminate()
            process.wait(timeout=10)


@pytest.fixture(scope="module")
def hosted_server(tmp_path_factory: pytest.TempPathFactory) -> Generator[HostedServer]:
    with serve(tmp_path_factory.mktemp("hosted-browser")) as server:
        yield server


def close_context(context: BrowserContext) -> None:
    if sys.exc_info()[0] is not None:
        artifacts = ROOT / "test-results"
        artifacts.mkdir(exist_ok=True)
        context.tracing.stop(path=str(artifacts / f"hosted-{uuid4().hex}.zip"))
    context.close()


@contextmanager
def player_browser(
    browser: Browser, server: HostedServer, credentials: IdentityCredentials | None = None
) -> Generator[tuple[BrowserContext, Page]]:
    context = browser.new_context(ignore_https_errors=True)
    context.tracing.start(screenshots=True, snapshots=True)
    try:
        if credentials:
            context.add_cookies(
                [
                    {
                        "name": COOKIE,
                        "value": credentials.session.token,
                        "url": server.url,
                        "secure": True,
                        "httpOnly": True,
                        "sameSite": "Lax",
                    }
                ]
            )
        yield context, context.new_page()
    finally:
        close_context(context)


def capture_requests(page: Page) -> list[str]:
    urls: list[str] = []
    page.on("request", lambda request: urls.append(request.url))
    return urls


def capture(page: Page, name: str) -> None:
    output = os.environ.get("SWAY_E2E_QA_DIR")
    if output:
        directory = Path(output)
        directory.mkdir(parents=True, exist_ok=True)
        width = page.viewport_size["width"] if page.viewport_size else 0
        page.screenshot(path=str(directory / f"{name}-{width}.png"), full_page=True)


def assert_no_overflow(page: Page) -> None:
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def create_player(page: Page, server: HostedServer, name: str) -> None:
    page.goto(server.url)
    assert_no_overflow(page)
    capture(page, "signup")
    page.get_by_label("Display name").fill(name)
    with page.expect_request("**/identity") as identity_request:
        page.get_by_role("button", name="Create player", exact=True).click()
    assert identity_request.value.headers.get("origin") == server.url
    expect(page.locator("#recovery-code")).to_be_visible()
    assert_no_overflow(page)
    capture(page, "recovery")
    page.get_by_role("link", name="Continue to your tables").click()


def active_table(server: HostedServer) -> tuple[list[IdentityCredentials], TableView]:
    service = server.service
    users = [
        service.identity.create_principal(service.identity.anonymous_session().token, name)
        for name in ("Alice", "Bob")
    ]
    table = service.create(users[0].session.token, ("human", "human"))
    invite = service.invite(users[0].session.token, table.game_id, 1)
    table = service.join(users[1].session.token, invite.invitation_id, invite.secret)
    for user in users:
        table = service.ready(user.session.token, table.game_id, table.lobby_revision)
    table = service.start(users[0].session.token, table.game_id, table.lobby_revision)
    assert table.pending_player is not None
    return users, table


def show_current(page: Page, server: HostedServer, table: TableView) -> None:
    page.goto(f"{server.url}/games/{table.game_id}")
    expect(page.locator("#decision-form")).to_be_visible()


@pytest.mark.parametrize("players", [2, 3, 4])
def test_independent_players_join_fragment_links_ready_and_start(
    browser: Browser, hosted_server: HostedServer, players: int
) -> None:
    contexts: list[BrowserContext] = []
    pages: list[Page] = []
    try:
        for _ in range(players):
            context = browser.new_context(
                ignore_https_errors=True,
                viewport={"width": 320 if players == 2 else 390, "height": 900},
            )
            context.tracing.start(screenshots=True, snapshots=True)
            contexts.append(context)
            pages.append(context.new_page())
        host = pages[0]
        create_player(host, hosted_server, "Alice")
        host.locator("#players").select_option(str(players))
        host.get_by_role("button", name="Create table", exact=True).click()
        expect(host.get_by_role("heading", name="Gather around")).to_be_visible()
        assert_no_overflow(host)
        capture(host, "lobby")
        table_url = host.url
        for index, guest in enumerate(pages[1:], 2):
            host.get_by_role("button", name=f"Invite seat {index}", exact=True).click()
            invitation = host.locator("#invitation-link").input_value()
            assert "#" in invitation
            requested = capture_requests(guest)
            guest.goto(invitation)
            expect(guest.get_by_role("heading", name="You're invited")).to_be_visible()
            assert_no_overflow(guest)
            assert "#" not in guest.url
            assert not any(invitation.split("#")[1] in url for url in requested)
            guest.get_by_label("Display name").fill(f"Guest {index}")
            guest.get_by_role("button", name="Join table", exact=True).click()
            expect(guest.locator("#recovery-code")).to_be_visible()
            guest.get_by_role("link", name="Continue to the table").click()
            host.goto(table_url)
            expect(host.get_by_text(f"Seat {index}: Guest {index}", exact=False)).to_be_visible()
        for page in pages:
            page.reload()
            page.get_by_role("button", name="I'm ready", exact=True).click()
            expect(page.get_by_role("button", name="Not ready", exact=True)).to_be_visible()
        host.reload()
        host.get_by_role("button", name="Start game", exact=True).click()
        expect(host.locator("#board")).to_be_visible()
        capture(host, "game")
        for page in pages[1:]:
            page.reload()
            expect(page.locator("#board")).to_be_visible()
        assert sum(page.locator("#decision-form").count() for page in pages) == 1
        for context in contexts:
            cookies = context.cookies()
            bearer = next(cookie for cookie in cookies if cookie.get("name") == COOKIE)
            assert (
                bearer.get("secure") and bearer.get("httpOnly") and bearer.get("sameSite") == "Lax"
            )
    finally:
        for context in contexts:
            close_context(context)


def test_theme_keeps_selected_choice_and_other_viewer_theme(
    browser: Browser, hosted_server: HostedServer
) -> None:
    users, table = active_table(hosted_server)
    assert table.pending_player is not None
    actor, observer = users[table.pending_player], users[1 - table.pending_player]
    with (
        player_browser(browser, hosted_server, actor) as (_, page),
        player_browser(browser, hosted_server, observer) as (_, other),
    ):
        show_current(page, hosted_server, table)
        other.goto(page.url)
        option = page.locator('#decision-form input[name="choices"]').first
        option.check()
        value = option.input_value()
        revision = page.locator("#table").get_attribute("data-revision")
        page.get_by_role("combobox", name="Theme", exact=True).select_option("orbital")
        page.get_by_role("button", name="Apply theme").click()
        expect(page.locator("#board")).to_have_attribute("data-theme", "orbital")
        expect(page.locator(f'#decision-form input[value="{value}"]')).to_be_checked()
        expect(page.locator("#confirm-choice")).to_be_enabled()
        expect(page.locator("#table")).to_have_attribute("data-revision", revision or "")
        other.reload()
        expect(other.locator("#board")).to_have_attribute("data-theme", "common-ground")


def test_lost_response_retries_identical_request_once(
    browser: Browser, hosted_server: HostedServer
) -> None:
    users, table = active_table(hosted_server)
    assert table.pending_player is not None
    with player_browser(browser, hosted_server, users[table.pending_player]) as (_, page):
        show_current(page, hosted_server, table)
        payloads: list[str] = []

        def lose_first_response(route: Route) -> None:
            payloads.append(route.request.post_data or "")
            response = route.fetch()
            if len(payloads) == 1:
                route.abort("failed")
            else:
                route.fulfill(response=response)

        page.route("**/decisions", lose_first_response)
        page.locator('#decision-form input[name="choices"]').first.check()
        page.locator("#confirm-choice").click()
        expect(page.get_by_role("button", name="Retry saved request")).to_be_visible()
        expect(page.locator("#confirm-choice")).to_be_disabled()
        page.get_by_role("button", name="Retry saved request").click()
        expect(page.get_by_role("button", name="Retry saved request")).to_have_count(0)
        expect(page.locator("#table")).to_have_attribute("data-revision", "1")
        assert len(payloads) == 2 and parse_qs(payloads[0]) == parse_qs(payloads[1])
        with hosted_server.service.store.transaction() as conn:
            assert (
                conn.execute(
                    "SELECT count(*) FROM hosted_commands WHERE game_id=?", (table.game_id,)
                ).fetchone()[0]
                == 1
            )


def test_delayed_poll_serializes_submit_and_cannot_overwrite_choice(
    browser: Browser, hosted_server: HostedServer
) -> None:
    users, table = active_table(hosted_server)
    assert table.pending_player is not None
    with player_browser(browser, hosted_server, users[table.pending_player]) as (_, page):
        show_current(page, hosted_server, table)
        waiting: list[Route] = []
        posts: list[Request] = []
        page.route("**/updates?*", lambda route: waiting.append(route))
        page.on(
            "request", lambda request: posts.append(request) if request.method == "POST" else None
        )
        page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        page.wait_for_timeout(100)
        assert len(waiting) == 1
        page.locator('#decision-form input[name="choices"]').first.check()
        page.locator("#confirm-choice").click()
        assert posts == []
        expect(page.locator("#confirm-choice")).to_be_disabled()
        waiting.pop().fulfill(status=204)
        expect(page.locator("#table")).to_have_attribute("data-revision", "1")
        assert len(posts) == 1
        page.unroute("**/updates?*")
        page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        expect(page.locator("#table")).to_have_attribute("data-revision", "1")


def test_offline_blocks_choice_and_unchanged_reconnect_unlocks(
    browser: Browser, hosted_server: HostedServer
) -> None:
    users, table = active_table(hosted_server)
    assert table.pending_player is not None
    with player_browser(browser, hosted_server, users[table.pending_player]) as (context, page):
        show_current(page, hosted_server, table)
        option = page.locator('#decision-form input[name="choices"]').first
        option.check()
        expect(page.locator("#confirm-choice")).to_be_enabled()
        context.set_offline(True)
        expect(page.locator("#confirm-choice")).to_be_disabled()
        page.locator('#decision-form input[name="choices"]').last.check()
        option.check()
        expect(page.locator("#confirm-choice")).to_be_disabled()
        context.set_offline(False)
        expect(page.locator("#confirm-choice")).to_be_enabled(timeout=10000)
        expect(option).to_be_checked()
        expect(page.locator("#table")).to_have_attribute("data-revision", "0")


def test_revoked_session_poll_clears_private_board(
    browser: Browser, hosted_server: HostedServer
) -> None:
    users, table = active_table(hosted_server)
    assert table.pending_player is not None
    actor = users[table.pending_player]
    with player_browser(browser, hosted_server, actor) as (_, page):
        show_current(page, hosted_server, table)
        hosted_server.service.identity.revoke_session(actor.session.token)
        page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        expect(
            page.get_by_text("Your access to this table has ended.", exact=False)
        ).to_be_visible()
        expect(page.locator("#board")).to_have_count(0)
        expect(page.locator("#decision-form")).to_have_count(0)


def test_reaction_is_private_to_target_and_survives_process_restart(
    browser: Browser, tmp_path: Path
) -> None:
    from sway.engine import Card, Command, Decision, Effect, GameConfig, Option, advance, new_game
    from sway.service import serialize_game

    directory = tmp_path / "reaction-server"
    contexts = [browser.new_context(ignore_https_errors=True) for _ in range(3)]
    for context in contexts:
        context.tracing.start(screenshots=True, snapshots=True)
    try:
        with serve(directory) as server:
            service = server.service
            users = [
                service.identity.create_principal(service.identity.anonymous_session().token, name)
                for name in ("Alice", "Bob", "Charlie")
            ]
            table = service.create(users[0].session.token, ("human", "human", "human"))
            for index in (1, 2):
                invitation = service.invite(users[0].session.token, table.game_id, index)
                table = service.join(
                    users[index].session.token, invitation.invitation_id, invitation.secret
                )
            for user in users:
                table = service.ready(user.session.token, table.game_id, table.lobby_revision)
            table = service.start(users[0].session.token, table.game_id, table.lobby_revision)
            state = new_game(
                GameConfig(player_count=3, player_names=("Alice", "Bob", "Charlie")), 2
            )
            attack = Card(f"c{state.next_instance_id}", "k14")
            protection = Card(f"c{state.next_instance_id + 1}", "k16")
            state.next_instance_id += 2
            state.supply["k14"] -= 1
            state.supply["k16"] -= 1
            state.players[0].hand.append(attack)
            state.players[1].hand.append(protection)
            assert state.pending is not None
            state.pending = Decision(
                state.pending.id,
                0,
                "menu",
                "action",
                (Option(attack.id, attack.definition, attack.id), Option("end-actions")),
                1,
                1,
            )
            state.pending_effect = Effect("action", 0)
            reaction = advance(state, Command(state.pending.id, state.revision, (attack.id,))).state
            assert reaction.pending is not None and reaction.pending.player == 1
            with service.store.transaction(write=True) as conn:
                conn.execute(
                    "UPDATE hosted_rooms SET revision=?,snapshot=? WHERE game_id=?",
                    (
                        reaction.revision,
                        serialize_game(reaction, (), frozenset({0, 1, 2})),
                        table.game_id,
                    ),
                )
            pages: list[Page] = []
            for context, user in zip(contexts, users, strict=True):
                context.add_cookies(
                    [
                        {
                            "name": COOKIE,
                            "value": user.session.token,
                            "url": server.url,
                            "secure": True,
                            "httpOnly": True,
                            "sameSite": "Lax",
                        }
                    ]
                )
                page = context.new_page()
                page.goto(f"{server.url}/games/{table.game_id}")
                pages.append(page)
            expect(pages[1].locator("#decision-heading")).to_have_text(
                "Protect yourself from this attack?"
            )
            decision = pages[1].locator("#decision-form").get_attribute("data-decision")
            for observer in (pages[0], pages[2]):
                assert "Protect yourself from this attack?" not in observer.content()
                expect(observer.locator("#decision-form")).to_have_count(0)
                assert protection.id not in observer.content()
            port = int(server.url.rsplit(":", 1)[1])
        with serve(directory, port=port):
            for page in pages:
                page.reload()
            expect(pages[1].locator("#decision-form")).to_have_attribute(
                "data-decision", decision or ""
            )
            pages[1].locator('#decision-form input[value="yes"]').check()
            pages[1].locator("#confirm-choice").click()
            expect(pages[1].locator("#table")).to_have_attribute(
                "data-revision", str(reaction.revision + 1)
            )
            assert "blocked the attack" in pages[1].locator(".history").inner_text()
    finally:
        for context in contexts:
            close_context(context)


def test_server_startup_discovers_bot_work_without_an_open_tab(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def seed(_bits: int) -> int:
        return 0

    monkeypatch.setattr("sway.hosting.service.secrets.randbits", seed)
    directory = tmp_path / "bot-server"
    directory.mkdir(mode=0o700)
    service = HostedServer("https://unused.example", directory).service
    host = service.identity.create_principal(service.identity.anonymous_session().token, "Alice")
    table = service.create(host.session.token, ("human", "engine", "attack"))
    table = service.ready(host.session.token, table.game_id, table.lobby_revision)
    table = service.start(host.session.token, table.game_id, table.lobby_revision)
    assert table.pending_player == 1 and table.revision == 0
    # No enqueue call or browser connection exists before the process starts.
    with serve(directory):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            table = service.view(host.session.token, table.game_id)
            if table.pending_player == 0:
                break
            time.sleep(0.05)
        assert table.pending_player == 0 and table.revision > 0
    revision = table.revision
    with serve(directory):
        assert service.view(host.session.token, table.game_id).revision == revision
