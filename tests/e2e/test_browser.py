"""Exercise real browser behaviour across HTMX updates and saved games."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from playwright.sync_api import Page, Request, expect

from sway.bots import BotState, choose
from sway.engine import GameConfig, new_game, state_to_json, view_for
from sway.engine.catalog import CATALOG
from sway.engine.models import Card, Decision, Effect, Option
from sway.presentation.components import BoardContext, choice_form
from sway.presentation.themes import load_themes
from sway.service import GameService
from sway.storage import SQLiteStore

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def server_data(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("browser-saves")


@contextmanager
def running_server(server_data: Path, *, developer_terminology: bool = False) -> Generator[str]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    environment = {
        **os.environ,
        "SWAY_DATA_DIR": str(server_data),
        "SWAY_DEV_TERMINOLOGY": "1" if developer_terminology else "0",
    }
    output_path = server_data / "browser-server.log"
    with (
        output_path.open("w") as output,
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "sway.web:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT,
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
        ) as process,
    ):
        try:
            for _ in range(100):
                if process.poll() is not None:
                    output.flush()
                    pytest.fail(output_path.read_text())
                try:
                    with urlopen(url, timeout=0.5) as response:
                        if response.status == 200:
                            break
                except (URLError, TimeoutError):
                    time.sleep(0.1)
            else:
                pytest.fail("Browser server did not start within ten seconds")
            yield url
        finally:
            process.terminate()
            process.wait(timeout=10)


@pytest.fixture(scope="module")
def server_url(server_data: Path) -> Iterator[str]:
    with running_server(server_data) as url:
        yield url


@pytest.fixture(scope="module")
def developer_server_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    with running_server(
        tmp_path_factory.mktemp("developer-browser-saves"), developer_terminology=True
    ) as url:
        yield url


def test_new_game_local_selection_theme_and_reload(page: Page, server_url: str) -> None:
    page.goto(server_url)
    page.get_by_role("button", name="Begin a game").click()
    expect(page.locator("#decision-form")).to_be_visible(timeout=15000)
    expect(page.locator("#board")).to_have_attribute("data-theme", "common-ground")
    expect(page.locator(".original-name")).to_have_count(0)
    location = page.url
    revision = page.locator("#board").get_attribute("data-revision")
    requests: list[str] = []

    def observe(request: Request) -> None:
        if request.method == "POST":
            requests.append(request.url)

    page.on("request", observe)
    options = page.locator('#decision-form input[name="choices"]')
    options.first.check()
    expect(page.get_by_role("button", name="Confirm choice")).to_be_enabled()
    assert requests == []
    page.get_by_role("button", name="Clear selection").click()
    expect(options.first).not_to_be_checked()
    options.last.check()
    page.get_by_role("button", name="Confirm choice").click()
    expect(page.locator("#board")).not_to_have_attribute("data-revision", revision or "")
    expect(page.locator("#decision-form")).to_be_visible(timeout=15000)
    settled_revision = page.locator("#board").get_attribute("data-revision")
    pending_option = page.locator('#decision-form input[name="choices"]').first
    pending_option.check()
    preserved_choice = pending_option.get_attribute("value")
    page.get_by_role("combobox", name="Theme", exact=True).select_option("orbital")
    page.get_by_role("button", name="Apply theme").click()
    expect(page.locator("#board")).to_have_attribute("data-theme", "orbital")
    expect(page.locator(".original-name")).to_have_count(0)
    expect(page.locator("#board")).to_have_attribute("data-revision", settled_revision or "")
    expect(page.locator(f'#decision-form input[value="{preserved_choice}"]')).to_be_checked()
    page.reload()
    expect(page.locator("#board")).to_have_attribute("data-theme", "orbital")
    expect(page.locator("#board")).to_have_attribute("data-revision", settled_revision or "")
    page.goto(server_url)
    page.locator(f'a[href="{location.removeprefix(server_url)}"]').click()
    expect(page.locator("#board")).to_have_attribute("data-theme", "orbital")


def test_developer_names_are_visible_after_theme_and_decision_updates(
    page: Page, developer_server_url: str
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(developer_server_url)
    page.locator("#supply-mode").select_option("manual")
    expect(
        page.locator("#manual-supply").get_by_text("Original: Village", exact=True)
    ).to_be_visible()
    page.locator("#supply-mode").select_option("starter")
    page.get_by_role("button", name="Begin a game").click()
    expect(page.locator("#decision-form")).to_be_visible(timeout=15000)
    supply_card = page.locator(".supply-grid .card-face").filter(has_text="Original: Village")
    expect(supply_card.locator(".original-name")).to_be_visible()
    expect(supply_card.locator("strong")).to_have_text("Crossroads")
    revision = page.locator("#board").get_attribute("data-revision")
    page.get_by_role("combobox", name="Theme", exact=True).select_option("orbital")
    page.get_by_role("button", name="Apply theme").click()
    expect(supply_card.locator("strong")).to_have_text("Waypoint")
    expect(supply_card.locator(".original-name")).to_be_visible()
    expect(page.locator("#board")).to_have_attribute("data-revision", revision or "")
    page.locator('#decision-form input[name="choices"]').last.focus()
    page.keyboard.press("Space")
    page.get_by_role("button", name="Confirm choice").click()
    expect(page.locator("#board")).not_to_have_attribute("data-revision", revision or "")
    expect(page.locator("#decision-form")).to_be_visible(timeout=15000)
    expect(supply_card.locator(".original-name")).to_be_visible()
    page.reload()
    expect(supply_card.locator("strong")).to_have_text("Waypoint")
    expect(supply_card.locator(".original-name")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_manual_setup_requires_ten_and_hides_extra_opponents(page: Page, server_url: str) -> None:
    page.goto(server_url)
    expect(page.locator('[data-opponent="2"]')).to_be_hidden()
    page.locator("#players").select_option("4")
    expect(page.locator('[data-opponent="3"]')).to_be_visible()
    page.locator("#supply-mode").select_option("manual")
    expect(page.locator("#manual-supply")).to_be_visible()
    page.get_by_role("button", name="Begin a game").click()
    expect(page.get_by_role("alert")).to_contain_text("exactly 10")


def test_multiselect_limits_and_ordering_are_local(page: Page) -> None:
    state = new_game(GameConfig(), 5)
    view = view_for(state, 0)
    themes = load_themes(frozenset(CATALOG))
    ctx = BoardContext("widget", "token", themes["common-ground"], tuple(themes.values()))
    choices = tuple(
        Option(f"option-{index}", card_id) for index, card_id in enumerate(("k04", "k05", "k12"))
    )
    decision = Decision("widget", 0, "select", "discard", choices, 2, 2)
    page.set_content(str(choice_form(decision, view, ctx)))
    page.add_script_tag(path=ROOT / "src/sway/static/app.js")
    page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))")
    inputs = page.locator('input[name="choices"]')
    confirm = page.get_by_role("button", name="Confirm choice")
    expect(confirm).to_be_disabled()
    inputs.nth(0).check()
    inputs.nth(1).check()
    expect(confirm).to_be_enabled()
    inputs.nth(2).check()
    expect(confirm).to_be_disabled()
    ordered = replace(decision, kind="order", ordered=True, minimum=3, maximum=3)
    page.set_content(str(choice_form(ordered, view, ctx)))
    page.add_script_tag(path=ROOT / "src/sway/static/app.js")
    page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))")
    page.get_by_role("button", name="Move Sanctuary earlier").click()
    assert page.locator('.order-item input[name="choices"]').evaluate_all(
        "elements => elements.map(element => element.value)"
    ) == ["option-1", "option-0", "option-2"]


@pytest.mark.parametrize("kind", ["supply", "yes_no", "menu"])
def test_single_choice_widgets_support_keyboard_and_confirmation(page: Page, kind: str) -> None:
    from typing import cast

    from sway.engine.models import DecisionKind

    state = new_game(GameConfig(), 5)
    view = view_for(state, 0)
    themes = load_themes(frozenset(CATALOG))
    ctx = BoardContext("widget", "token", themes["common-ground"], tuple(themes.values()))
    options = (
        (Option("yes"), Option("no"))
        if kind == "yes_no"
        else (Option("k04", "k04"), Option("k05", "k05"))
    )
    decision = Decision("keyboard", 0, cast(DecisionKind, kind), "gain", options, 1, 1)
    page.set_content(str(choice_form(decision, view, ctx)))
    page.add_script_tag(path=ROOT / "src/sway/static/app.js")
    page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))")
    radio = page.locator('input[name="choices"]').first
    radio.focus()
    page.keyboard.press("Space")
    expect(radio).to_be_checked()
    expect(page.get_by_role("button", name="Confirm choice")).to_be_enabled()
    page.get_by_role("button", name="Clear selection").click()
    expect(page.get_by_role("button", name="Confirm choice")).to_be_disabled()


@pytest.mark.parametrize(("prompt", "minimum", "maximum"), [("militia", 2, 2), ("cellar", 0, 5)])
def test_ordered_subset_selects_only_checked_cards(
    page: Page, prompt: str, minimum: int, maximum: int
) -> None:
    state = new_game(GameConfig(), 5)
    view = view_for(state, 0)
    themes = load_themes(frozenset(CATALOG))
    ctx = BoardContext("widget", "token", themes["common-ground"], tuple(themes.values()))
    options = tuple(
        Option(f"card-{index}", card_id)
        for index, card_id in enumerate(("k04", "k05", "k12", "k13", "k14"))
    )
    decision = Decision("subset", 0, "select", prompt, options, minimum, maximum, ordered=True)
    page.set_content(str(choice_form(decision, view, ctx)))
    page.add_script_tag(path=ROOT / "src/sway/static/app.js")
    page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))")
    checked = page.locator('input[name="choices"]:checked')
    expect(checked).to_have_count(0)
    confirm = page.get_by_role("button", name="Confirm choice")
    if minimum == 0:
        expect(confirm).to_be_enabled()
    else:
        expect(confirm).to_be_disabled()
    page.locator('input[value="card-0"]').check()
    page.locator('input[value="card-1"]').check()
    expect(confirm).to_be_enabled()
    page.get_by_role("button", name="Move Sanctuary earlier").click()
    selected = page.locator("#decision-form").evaluate(
        "form => new FormData(form).getAll('choices')"
    )
    assert selected == ["card-1", "card-0"]
    page.get_by_role("button", name="Clear selection").click()
    expect(checked).to_have_count(0)


def test_complete_game_reaches_scoring_and_saved_result(
    page: Page, server_url: str, server_data: Path
) -> None:
    """A heuristic assists the human seat but every move goes through the real UI."""
    page.goto(server_url)
    page.locator('input[name="seed"]').fill("17")
    page.get_by_role("button", name="Begin a game").click()
    page.wait_for_url("**/games/*")
    identifier = page.url.rsplit("/", 1)[1]
    service = GameService(SQLiteStore(server_data / "games.sqlite3"))
    memory = BotState("economy", 91)
    for _ in range(400):
        page.wait_for_selector("#decision-form, .finished", timeout=15000)
        if page.locator(".finished").count():
            break
        view = service.view(identifier)
        assert view.pending is not None
        result = choose(view, view.pending, memory)
        memory = result.state
        for selected in result.command.selections:
            control = page.locator(f'#decision-form input[name="choices"][value="{selected}"]')
            if control.get_attribute("type") != "hidden":
                control.check()
        revision = page.locator("#board").get_attribute("data-revision")
        page.get_by_role("button", name="Confirm choice").click()
        expect(page.locator("#board")).not_to_have_attribute("data-revision", revision or "")
    else:
        pytest.fail("The browser game did not finish within 400 human decisions")
    expect(page.locator(".finished")).to_contain_text("points")
    expected_scores = service.view(identifier).scores
    assert len(expected_scores) == 2
    page.reload()
    expect(page.locator(".finished")).to_contain_text("points")
    assert service.view(identifier).scores == expected_scores


def test_bot_attack_stops_for_human_reaction_and_survives_reload(
    page: Page, server_url: str, server_data: Path
) -> None:
    """Resume a legal attack setup; the opponent must wait for the human's reply."""
    state = new_game(GameConfig(player_names=("You", "Attacker")), 21)
    state.active_player = 1
    state.phase = "action"
    protection = Card(f"c{state.next_instance_id}", "k16")
    attack = Card(f"c{state.next_instance_id + 1}", "k14")
    state.next_instance_id += 2
    state.supply["k16"] -= 1
    state.supply["k14"] -= 1
    state.players[0].hand.append(protection)
    state.players[1].hand.append(attack)
    assert state.pending is not None
    state.pending = Decision(
        state.pending.id,
        1,
        "menu",
        "action",
        (Option(attack.id, attack.definition, attack.id), Option("end-actions")),
        1,
        1,
    )
    state.pending_effect = Effect("action", 1)
    identifier = "browser-reaction"
    store = SQLiteStore(server_data / "games.sqlite3")
    store.create(
        identifier,
        json.dumps(
            {"schema": 1, "engine": state_to_json(state), "bots": [asdict(BotState("attack", 91))]}
        ),
        json.dumps({"players": ["You", "Attacker"]}),
        "common-ground",
    )
    page.goto(f"{server_url}/games/{identifier}")
    expect(page.locator("#decision-heading")).to_have_text("Protect yourself from this attack?")
    decision = page.locator("#decision-form").get_attribute("data-decision")
    revision = page.locator("#board").get_attribute("data-revision")
    page.reload()
    expect(page.locator("#decision-form")).to_have_attribute("data-decision", decision or "")
    expect(page.locator("#board")).to_have_attribute("data-revision", revision or "")
    page.locator('#decision-form input[value="yes"]').check()
    page.get_by_role("button", name="Confirm choice").click()
    expect(page.locator("#decision-form")).not_to_have_attribute("data-decision", decision or "")
    service = GameService(store)
    assert len(service.load(identifier).state.players[0].hand) == 6
    expect(page.locator(".history")).to_contain_text("blocked the attack")


def test_stale_tab_shows_current_game_without_repeating_move(
    page: Page, server_url: str, server_data: Path
) -> None:
    page.goto(server_url)
    page.locator('input[name="seed"]').fill("13")
    page.get_by_role("button", name="Begin a game").click()
    expect(page.locator("#decision-form")).to_be_visible(timeout=15000)
    identifier = page.url.rsplit("/", 1)[1]
    stale = page.context.new_page()
    try:
        stale.goto(page.url)
        stale.locator('#decision-form input[value="play-treasures"]').check()
        page.locator('#decision-form input[value="play-treasures"]').check()
        old_revision = page.locator("#board").get_attribute("data-revision")
        page.get_by_role("button", name="Confirm choice").click()
        expect(page.locator("#board")).not_to_have_attribute("data-revision", old_revision or "")
        service = GameService(SQLiteStore(server_data / "games.sqlite3"))
        accepted = service.load(identifier)
        stale.get_by_role("button", name="Confirm choice").click()
        expect(stale.get_by_role("alert")).to_contain_text("The table has changed")
        expect(stale.locator("#board")).to_have_attribute("data-revision", str(accepted.revision))
        assert service.load(identifier) == accepted
    finally:
        stale.close()
