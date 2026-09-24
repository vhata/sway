"""Local HTML application. Rules and persistence live behind GameService."""

from __future__ import annotations

import os
import random
import secrets
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

import htpy as h
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData
from starlette.middleware.trustedhost import TrustedHostMiddleware

from sway.engine import Command, GameConfig, InvalidCommand
from sway.engine.catalog import CATALOG, KINGDOM_IDS
from sway.presentation.components import BoardContext, SavedGame, SetupValues, board, home, page
from sway.presentation.reference import card_reference
from sway.presentation.themes import STATIC_ROOT, Theme, load_themes
from sway.service import GameRecord, GameService, GameSummary
from sway.storage import GameNotFound, SQLiteStore, StorageConflict, StorageError

COOKIE = "sway_csrf"


def _field(data: FormData, key: str, default: str = "") -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"Invalid {key} field")
    return value


def _setup_values(data: FormData, default_theme: str) -> SetupValues:
    """Keep text entries for correction without treating them as valid setup."""

    def text_field(key: str, default: str) -> str:
        value = data.get(key, default)
        return value if isinstance(value, str) else default

    return SetupValues(
        players=text_field("players", "2"),
        seed=text_field("seed", "42"),
        theme=text_field("theme", default_theme),
        supply=text_field("supply", "starter"),
        strategies=tuple(
            text_field(f"strategy{index}", default)
            for index, default in enumerate(("economy", "engine", "attack"), 1)
        ),
        kingdom=tuple(value for value in data.getlist("kingdom") if isinstance(value, str)),
    )


def _csrf(request: Request) -> str:
    return request.cookies.get(COOKIE) or secrets.token_urlsafe(32)


def _response(request: Request, node: h.Node, token: str, status: int = 200) -> HTMLResponse:
    response = HTMLResponse(str(node), status_code=status)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if request.cookies.get(COOKIE) != token:
        response.set_cookie(
            COOKIE, token, httponly=True, samesite="strict", secure=request.url.scheme == "https"
        )
    return response


def _check_mutation(request: Request, data: FormData) -> None:
    cookie = request.cookies.get(COOKIE, "")
    token = _field(data, "csrf")
    if not cookie or not secrets.compare_digest(cookie, token):
        raise PermissionError("This form expired. Reload the page and try again.")
    origin = request.headers.get("origin")
    if origin:
        expected = urlsplit(str(request.url))
        actual = urlsplit(origin)
        if (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc):
            raise PermissionError("Requests from another site are not accepted.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise PermissionError("Requests from another site are not accepted.")


def _metadata(record: GameRecord | GameSummary) -> SavedGame:
    return SavedGame(
        record.game_id,
        record.revision,
        record.theme_id,
        record.status,
        record.updated_at,
        record.player_names,
    )


def create_app(data_dir: Path | None = None) -> FastAPI:
    developer_terminology = os.environ.get("SWAY_DEV_TERMINOLOGY") == "1"
    directory = data_dir or Path(
        os.environ.get("SWAY_DATA_DIR", str(Path.home() / ".local/share/sway"))
    )
    themes = load_themes(frozenset(CATALOG))
    default_theme = themes.get("common-ground", next(iter(themes.values())))
    service: GameService | None = None
    service_lock = Lock()
    application = FastAPI(title="Sway", docs_url=None, redoc_url=None, openapi_url=None)
    application.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"]
    )
    application.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")

    def get_service() -> GameService:
        nonlocal service
        with service_lock:
            if service is None:
                directory.mkdir(parents=True, exist_ok=True)
                service = GameService(SQLiteStore(directory / "games.sqlite3"))
            return service

    def get_theme(identifier: str) -> Theme:
        if identifier not in themes:
            raise ValueError("Choose an available theme.")
        return themes[identifier]

    def render_game(
        request: Request, game_id: str, error: str | None = None, status: int = 200
    ) -> HTMLResponse:
        current_service = get_service()
        pause_bots = error is not None
        record = current_service.load(game_id)
        theme = themes.get(record.theme_id, default_theme)
        if record.theme_id not in themes:
            fallback_notice = (
                f"Your saved theme is unavailable; showing {theme.name}. Your game is unchanged."
            )
            error = f"{error} {fallback_notice}" if error else fallback_notice
        view = current_service.view(game_id)
        token = _csrf(request)
        content = board(
            view,
            BoardContext(
                game_id,
                token,
                theme,
                tuple(themes.values()),
                error,
                pause_bots,
                developer_terminology=developer_terminology,
            ),
        )
        node = (
            content if request.headers.get("HX-Request") == "true" else page("Your table", content)
        )
        return _response(request, node, token, status)

    @application.exception_handler(GameNotFound)
    async def missing(request: Request, _exc: GameNotFound) -> HTMLResponse:
        return _response(
            request,
            page(
                "Table not found",
                h.main(id="main", class_="home")[
                    h.h1["This table could not be found."], h.a(href="/")["Return to your games"]
                ],
            ),
            _csrf(request),
            404,
        )

    @application.exception_handler(StorageError)
    async def save_error(request: Request, _exc: StorageError) -> HTMLResponse:
        return _response(
            request,
            page(
                "Save unavailable",
                h.main(id="main", class_="home")[
                    h.h1["This save cannot be opened."],
                    h.p[
                        "The save uses an unsupported format or could not be read. Its original contents have been preserved."
                    ],
                    h.a(href="/")["Return to your games"],
                ],
            ),
            _csrf(request),
            422,
        )

    @application.exception_handler(PermissionError)
    async def denied(request: Request, exc: PermissionError) -> HTMLResponse:
        return _response(
            request,
            page(
                "Request blocked",
                h.main(id="main", class_="home")[
                    h.h1["Please reload your table."],
                    h.p[str(exc)],
                    h.a(href="/")["Return to your games"],
                ],
            ),
            _csrf(request),
            403,
        )

    @application.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        token = _csrf(request)
        games = [_metadata(game) for game in get_service().list_games()]
        return _response(
            request,
            home(games, tuple(themes.values()), token, developer_terminology=developer_terminology),
            token,
        )

    @application.get("/developer/cards", response_class=HTMLResponse)
    def reference(request: Request, theme: str | None = None) -> HTMLResponse:
        token = _csrf(request)
        if not developer_terminology:
            return _response(
                request,
                page("Page not found", h.main(id="main", class_="home")[h.h1["Page not found."]]),
                token,
                404,
            )
        if theme is not None and theme not in themes:
            return _response(
                request,
                page(
                    "Theme unavailable",
                    h.main(id="main", class_="home")[
                        h.h1["Choose an available theme."],
                        h.a(href="/developer/cards")["Return to the card catalogue"],
                    ],
                ),
                token,
                422,
            )
        return _response(
            request,
            card_reference(themes[theme] if theme else default_theme, tuple(themes.values())),
            token,
        )

    @application.post("/games", response_model=None)
    async def create_game(request: Request) -> HTMLResponse | RedirectResponse:
        data = await request.form()
        _check_mutation(request, data)
        try:
            count = int(_field(data, "players", "2"))
            if count not in {2, 3, 4}:
                raise ValueError("Choose between 2 and 4 players.")
            seed = int(_field(data, "seed", "42"))
            if not 0 <= seed < 2**63:
                raise ValueError("Choose a seed between 0 and 9223372036854775807.")
            strategies = tuple(
                _field(data, f"strategy{index}", "economy") for index in range(1, count)
            )
            theme = get_theme(_field(data, "theme", default_theme.id))
            supply = _field(data, "supply", "starter")
            kingdom = GameConfig().kingdom
            if supply == "random":
                kingdom = tuple(random.Random(seed).sample(KINGDOM_IDS, 10))
            elif supply == "manual":
                choices = data.getlist("kingdom")
                kingdom = tuple(value for value in choices if isinstance(value, str))
                if (
                    len(kingdom) != 10
                    or len(set(kingdom)) != 10
                    or not set(kingdom) <= set(KINGDOM_IDS)
                ):
                    raise ValueError("Choose exactly 10 different supply cards.")
            elif supply != "starter":
                raise ValueError("Choose an available supply mode.")
            names = ("You",) + tuple(
                f"{strategy.capitalize()} {index}" for index, strategy in enumerate(strategies, 1)
            )
            config = GameConfig(player_count=count, kingdom=kingdom, player_names=names)
            record = await run_in_threadpool(
                get_service().create, config, seed, strategies, theme.id
            )
        except ValueError as exc:
            token = _csrf(request)
            games = [_metadata(game) for game in get_service().list_games()]
            return _response(
                request,
                home(
                    games,
                    tuple(themes.values()),
                    token,
                    str(exc),
                    developer_terminology=developer_terminology,
                    setup=_setup_values(data, default_theme.id),
                ),
                token,
                422,
            )
        return RedirectResponse(f"/games/{record.game_id}", status_code=303)

    @application.get("/games/{game_id}", response_class=HTMLResponse)
    def show_game(request: Request, game_id: str) -> HTMLResponse:
        return render_game(request, game_id)

    @application.post("/games/{game_id}/decisions", response_class=HTMLResponse)
    async def submit_decision(request: Request, game_id: str) -> HTMLResponse:
        data = await request.form()
        _check_mutation(request, data)
        try:
            selected = data.getlist("choices")
            if not all(isinstance(value, str) for value in selected):
                raise ValueError("Choose valid options.")
            command = Command(
                _field(data, "decision"),
                int(_field(data, "revision")),
                tuple(value for value in selected if isinstance(value, str)),
            )
            await run_in_threadpool(get_service().submit, game_id, command)
        except (StorageConflict, InvalidCommand) as exc:
            return render_game(
                request, game_id, f"The table has changed or this choice is unavailable. {exc}", 409
            )
        except ValueError:
            return render_game(request, game_id, "Choose a valid option, then try again.", 422)
        return render_game(request, game_id)

    @application.post("/games/{game_id}/advance", response_class=HTMLResponse)
    async def advance_opponents(request: Request, game_id: str) -> HTMLResponse:
        data = await request.form()
        _check_mutation(request, data)
        try:
            await run_in_threadpool(
                get_service().advance_bots, game_id, int(_field(data, "revision")), 8
            )
        except StorageConflict:
            return render_game(
                request,
                game_id,
                "Another tab already advanced this table. The latest game is shown.",
                409,
            )
        except (InvalidCommand, ValueError, RuntimeError):
            return render_game(
                request,
                game_id,
                "An opponent could not complete its move. Your last successful move is saved; retry to continue.",
                422,
            )
        return render_game(request, game_id)

    @application.post("/games/{game_id}/theme", response_class=HTMLResponse)
    async def change_theme(request: Request, game_id: str) -> HTMLResponse:
        data = await request.form()
        _check_mutation(request, data)
        try:
            theme = get_theme(_field(data, "theme"))
            await run_in_threadpool(get_service().set_theme, game_id, theme.id)
        except ValueError:
            return render_game(
                request, game_id, "This theme is unavailable. Your current theme is unchanged.", 422
            )
        return render_game(request, game_id)

    return application


app = create_app()
