"""Exercise real browser behaviour across HTMX updates and saved games."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from playwright.sync_api import Page, Request, expect

from sway.engine import GameConfig, new_game, view_for
from sway.engine.catalog import CATALOG
from sway.engine.models import Decision, Option
from sway.presentation.components import BoardContext, choice_form
from sway.presentation.themes import load_themes

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def server_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    environment = {**os.environ, "SWAY_DATA_DIR": str(tmp_path_factory.mktemp("browser-saves"))}
    with subprocess.Popen(
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
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ) as process:
        try:
            for _ in range(100):
                if process.poll() is not None:
                    assert process.stdout is not None
                    pytest.fail(process.stdout.read().decode())
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


def test_new_game_local_selection_theme_and_reload(page: Page, server_url: str) -> None:
    page.goto(server_url)
    page.get_by_role("button", name="Begin a game").click()
    expect(page.locator("#decision-form")).to_be_visible(timeout=15000)
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
    page.get_by_role("combobox", name="Theme", exact=True).select_option("orbital")
    page.get_by_role("button", name="Apply theme").click()
    expect(page.locator("#board")).to_have_attribute("data-theme", "orbital")
    expect(page.locator("#board")).to_have_attribute("data-revision", settled_revision or "")
    page.reload()
    expect(page.locator("#board")).to_have_attribute("data-theme", "orbital")
    expect(page.locator("#board")).to_have_attribute("data-revision", settled_revision or "")
    page.goto(server_url)
    page.locator(f'a[href="{location.removeprefix(server_url)}"]').click()
    expect(page.locator("#board")).to_have_attribute("data-theme", "orbital")


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
    ctx = BoardContext("widget", "token", themes["neutral"], tuple(themes.values()))
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
    ctx = BoardContext("widget", "token", themes["neutral"], tuple(themes.values()))
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
