"""Explicit hosted entrypoint; the local application never mounts these routes."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

import htpy as h
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.datastructures import FormData

from sway.engine import Command, GameConfig, InvalidCommand
from sway.engine.catalog import CATALOG, KINGDOM_IDS
from sway.hosting.http import HostedBoundary
from sway.hosting.identity import AuthenticationError, Session, SessionCredentials
from sway.hosting.presentation import (
    SetupEntries,
    account,
    home,
    hosted_page,
    invitation,
    table_content,
)
from sway.hosting.runtime import HostedRuntime, WebConfig
from sway.hosting.service import TableView
from sway.presentation.themes import load_themes
from sway.storage import GameNotFound, StorageConflict

if TYPE_CHECKING:
    from sway.hosting.config import HostedConfig

COOKIE = "__Host-sway_session"


def _field(data: FormData, key: str, default: str = "") -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise ValueError("Choose valid form values.")
    return value


def _setup(data: FormData) -> tuple[tuple[str, ...], tuple[str, ...]]:
    count = int(_field(data, "players", "2"))
    if count not in {2, 3, 4}:
        raise ValueError("Choose two to four players.")
    controllers = ("human",) + tuple(
        _field(data, f"controller{index}", "human") for index in range(1, count)
    )
    supply = _field(data, "supply", "starter")
    if supply == "starter":
        kingdom = GameConfig().kingdom
    elif supply == "random":
        kingdom = tuple(secrets.SystemRandom().sample(KINGDOM_IDS, 10))
    elif supply == "manual":
        kingdom = tuple(value for value in data.getlist("kingdom") if isinstance(value, str))
    else:
        raise ValueError("Choose an available supply mode.")
    if len(kingdom) != 10 or len(set(kingdom)) != 10 or not set(kingdom) <= set(KINGDOM_IDS):
        raise ValueError("Choose ten different supply cards.")
    return controllers, kingdom


def create_app(config: HostedConfig | None = None) -> FastAPI:
    """Compatibility entrypoint for the laptop/VM deployment."""
    from sway.hosting.selfhost import create_selfhost_app

    return create_selfhost_app(config)


def create_application(settings: WebConfig, runtime: HostedRuntime) -> FastAPI:
    """The same routes, privacy rules and browser experience on either runtime."""
    identity, service = runtime.identity, runtime.service
    themes = tuple(load_themes(frozenset(CATALOG)).values())
    application = FastAPI(
        title="Sway private tables",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=runtime.lifespan,
    )
    application.add_middleware(HostedBoundary, config=settings, limiter=runtime.limiter)
    if runtime.assets is not None:
        application.mount("/static", runtime.assets, name="static")

    def token(request: Request) -> str:
        return request.cookies.get(COOKIE, "")

    async def session(request: Request) -> Session:
        return await runtime.execute(identity.authenticate, token(request))

    def cookie(response: Response, credentials: SessionCredentials) -> Response:
        response.set_cookie(
            COOKIE,
            credentials.token,
            secure=True,
            httponly=True,
            samesite="lax",
            path="/",
            max_age=max(1, int(credentials.session.expires_at - runtime.clock())),
        )
        return response

    async def anonymous(request: Request) -> tuple[Session, SessionCredentials | None]:
        try:
            return await session(request), None
        except AuthenticationError:
            credentials = await runtime.execute(identity.anonymous_session)
            return credentials.session, credentials

    async def render(
        request: Request, table: TableView, error: str | None = None, status: int = 200
    ) -> HTMLResponse:
        content = table_content(table, (await session(request)).csrf_token, themes, error)
        node = (
            content
            if request.headers.get("HX-Request") == "true"
            else hosted_page("Your table", content)
        )
        return HTMLResponse(str(node), status_code=status)

    async def mutation(request: Request) -> FormData:
        data = await request.form(max_fields=100)
        current = await session(request)
        if not secrets.compare_digest(current.csrf_token.encode(), _field(data, "csrf").encode()):
            raise PermissionError("This form expired. Reload before trying again.")
        return data

    @application.exception_handler(PermissionError)
    async def stale_form(_request: Request, _exc: PermissionError) -> HTMLResponse:
        return HTMLResponse(
            str(
                hosted_page(
                    "Reload your table",
                    h.main(id="main", class_="home")[
                        h.h1["This form has expired"],
                        h.p["Reload your table to continue with your current player."],
                        h.a(href="/")["Your tables"],
                    ],
                )
            ),
            status_code=403,
        )

    @application.exception_handler(AuthenticationError)
    async def expired(_request: Request, _exc: AuthenticationError) -> HTMLResponse:
        response = HTMLResponse(
            str(
                hosted_page(
                    "Please sign in",
                    h.main(id="main", class_="home")[
                        h.h1["Your session has ended"],
                        h.p["Sign in with your recovery code to return to your tables."],
                        h.a(href="/account")["Your player"],
                    ],
                )
            ),
            status_code=401,
        )
        response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="lax")
        return response

    @application.exception_handler(GameNotFound)
    async def missing(_request: Request, _exc: GameNotFound) -> HTMLResponse:
        return HTMLResponse(
            str(
                hosted_page(
                    "Table unavailable",
                    h.main(id="main", class_="home")[
                        h.h1["This table is unavailable"], h.a(href="/")["Your tables"]
                    ],
                )
            ),
            status_code=404,
        )

    @application.exception_handler(ValueError)
    async def invalid(_request: Request, exc: ValueError) -> HTMLResponse:
        return HTMLResponse(
            str(
                hosted_page(
                    "Check your choices",
                    h.main(id="main", class_="home")[
                        h.h1["Check your choices"], h.p[str(exc)], h.a(href="/")["Your tables"]
                    ],
                )
            ),
            status_code=422,
        )

    @application.get("/", response_model=None)
    async def index(request: Request) -> Response:
        current, credentials = await anonymous(request)
        if current.principal_id is None:
            response = HTMLResponse(str(account(current.csrf_token, False)))
        else:
            response = HTMLResponse(
                str(
                    home(
                        await runtime.execute(service.list_tables, token(request)),
                        current.csrf_token,
                        themes,
                    )
                )
            )
        return cookie(response, credentials) if credentials else response

    @application.get("/account", response_model=None)
    async def account_page(request: Request) -> Response:
        current, credentials = await anonymous(request)
        response = HTMLResponse(str(account(current.csrf_token, current.principal_id is not None)))
        return cookie(response, credentials) if credentials else response

    @application.post("/identity", response_model=None)
    async def create_identity(request: Request) -> Response:
        data = await mutation(request)
        credentials = await runtime.execute(
            identity.create_principal, token(request), _field(data, "display_name")
        )
        return cookie(
            HTMLResponse(
                str(
                    account(credentials.session.session.csrf_token, True, credentials.recovery_code)
                )
            ),
            credentials.session,
        )

    @application.post("/recover", response_model=None)
    async def recover(request: Request) -> Response:
        data = await mutation(request)
        credentials = await runtime.execute(
            identity.recover, token(request), _field(data, "recovery_code")
        )
        return cookie(
            HTMLResponse(
                str(
                    account(credentials.session.session.csrf_token, True, credentials.recovery_code)
                )
            ),
            credentials.session,
        )

    @application.post("/logout", response_model=None)
    async def logout(request: Request) -> Response:
        await mutation(request)
        await runtime.execute(identity.revoke_session, token(request))
        response = RedirectResponse("/account", status_code=303)
        response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="lax")
        return response

    @application.post("/games", response_model=None)
    async def create_table(request: Request) -> Response:
        data = await mutation(request)
        try:
            controllers, kingdom = _setup(data)
            table = await runtime.execute(service.create, token(request), controllers, kingdom)
        except ValueError as exc:
            entered = SetupEntries(
                _field(data, "players", "2"),
                tuple(_field(data, f"controller{index}", "human") for index in (1, 2, 3)),
                _field(data, "supply", "starter"),
                tuple(value for value in data.getlist("kingdom") if isinstance(value, str)),
            )
            tables = await runtime.execute(service.list_tables, token(request))
            current = await session(request)
            return HTMLResponse(
                str(home(tables, current.csrf_token, themes, entered=entered, error=str(exc))),
                status_code=422,
            )
        return RedirectResponse(f"/games/{table.game_id}", status_code=303)

    @application.get("/games/{game_id}", response_model=None)
    async def show(request: Request, game_id: str) -> Response:
        return await render(request, await runtime.execute(service.view, token(request), game_id))

    @application.get("/games/{game_id}/updates", response_model=None)
    async def updates(request: Request, game_id: str) -> Response:
        table = await runtime.execute(service.view, token(request), game_id)
        versions = (str(table.revision), str(table.lobby_revision), str(table.preference_version))
        if versions == tuple(
            request.query_params.get(key)
            for key in ("revision", "lobby_revision", "preference_version")
        ):
            return Response(status_code=204)
        return await render(request, table)

    @application.post("/games/{game_id}/{action}", response_model=None)
    async def table_action(request: Request, game_id: str, action: str) -> Response:
        data = await mutation(request)
        bearer = token(request)
        try:
            if action == "decisions":
                choices = tuple(
                    value for value in data.getlist("choices") if isinstance(value, str)
                )
                result = await runtime.execute(
                    service.submit,
                    bearer,
                    game_id,
                    _field(data, "request_id"),
                    Command(_field(data, "decision"), int(_field(data, "revision")), choices),
                )
                table = result.table
            elif action == "theme":
                theme = _field(data, "theme")
                if theme not in {pack.id for pack in themes}:
                    raise ValueError("Choose an available theme.")
                table = await runtime.execute(
                    service.set_theme,
                    bearer,
                    game_id,
                    theme,
                    int(_field(data, "preference_version")),
                )
            elif action == "ready":
                table = await runtime.execute(
                    service.ready,
                    bearer,
                    game_id,
                    int(_field(data, "lobby_revision")),
                    _field(data, "ready") == "true",
                )
            elif action == "start":
                table = await runtime.execute(
                    service.start, bearer, game_id, int(_field(data, "lobby_revision"))
                )
            elif action == "configure":
                controllers, kingdom = _setup(data)
                table = await runtime.execute(
                    service.configure,
                    bearer,
                    game_id,
                    int(_field(data, "lobby_revision")),
                    controllers,
                    kingdom,
                )
            elif action == "remove":
                table = await runtime.execute(
                    service.remove,
                    bearer,
                    game_id,
                    int(_field(data, "seat")),
                    int(_field(data, "lobby_revision")),
                )
            elif action == "cancel":
                table = await runtime.execute(service.cancel, bearer, game_id)
            elif action == "retry":
                table = await runtime.execute(service.retry_bots, bearer, game_id)
            elif action == "revoke-invite":
                await runtime.execute(
                    service.revoke_invite, bearer, game_id, int(_field(data, "seat"))
                )
                table = await runtime.execute(service.view, bearer, game_id)
            elif action == "invite":
                invite = await runtime.execute(
                    service.invite, bearer, game_id, int(_field(data, "seat"))
                )
                link = f"{settings.origin}/join/{invite.invitation_id}#{invite.secret}"
                return HTMLResponse(
                    str(
                        hosted_page(
                            "Invite a friend",
                            h.main(id="main", class_="home")[
                                h.h1["Invite a friend"],
                                h.p["This link works once, for 24 hours. Share it privately."],
                                h.label[
                                    "Invitation link",
                                    h.input(id="invitation-link", readonly=True, value=link),
                                ],
                                h.a(href=f"/games/{game_id}")["Return to the table"],
                            ],
                        )
                    )
                )
            else:
                raise GameNotFound("Unknown action.")
        except (StorageConflict, InvalidCommand) as exc:
            table = await runtime.execute(service.view, bearer, game_id)
            return await render(request, table, str(exc), 409)
        except ValueError as exc:
            table = await runtime.execute(service.view, bearer, game_id)
            return await render(request, table, str(exc), 422)
        if (
            table.status == "active"
            and table.pending_player is not None
            and table.seats[table.pending_player].controller != "human"
        ):
            await runtime.notify(table.game_id)
        return await render(request, table)

    @application.get("/join/{invitation_id}", response_model=None)
    async def join_page(request: Request, invitation_id: str) -> Response:
        current, credentials = await anonymous(request)
        response = HTMLResponse(
            str(invitation(current.csrf_token, invitation_id, current.principal_id is not None))
        )
        return cookie(response, credentials) if credentials else response

    @application.post("/join/{invitation_id}", response_model=None)
    async def join(request: Request, invitation_id: str) -> Response:
        data = await mutation(request)
        current = await session(request)
        if current.principal_id is None:
            credentials, table = await runtime.execute(
                service.join_guest,
                token(request),
                invitation_id,
                _field(data, "secret"),
                _field(data, "display_name"),
            )
            response = HTMLResponse(
                str(
                    hosted_page(
                        "Welcome to the table",
                        h.main(id="main", class_="home")[
                            h.h1["Your seat is saved"],
                            h.p["Keep this recovery code private. It is shown only once."],
                            h.code(id="recovery-code")[credentials.recovery_code],
                            h.p[h.a(href=f"/games/{table.game_id}")["Continue to the table"]],
                        ],
                    )
                )
            )
            return cookie(response, credentials.session)
        table = await runtime.execute(
            service.join, token(request), invitation_id, _field(data, "secret")
        )
        return RedirectResponse(f"/games/{table.game_id}", status_code=303)

    return application
