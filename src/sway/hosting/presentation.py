"""Hosted lobby and account pages consume only filtered service results."""

from __future__ import annotations

import htpy as h

from sway.bots import STRATEGIES
from sway.engine.catalog import KINGDOM_IDS
from sway.hosting.service import TableView
from sway.presentation.components import BoardContext, board, csrf_input, page
from sway.presentation.themes import Theme


def hosted_page(title: str, content: h.Node) -> h.Element:
    return page(title, h.div[content, h.script(src="/static/hosted.js", defer=True)])


def form(path: str, csrf: str, label: str, *fields: h.Node) -> h.Element:
    return h.form(action=path, method="post")[
        csrf_input(csrf), fields, h.button(type="submit", class_="secondary")[label]
    ]


def hidden(name: str, value: str | int) -> h.VoidElement:
    return h.input(type="hidden", name=name, value=str(value))


def account(csrf: str, authenticated: bool, recovery: str | None = None) -> h.Element:
    return hosted_page(
        "Your player",
        h.main(id="main", class_="home")[
            h.h1["Your place at the table"],
            h.section(class_="panel")[
                h.h2["Save your recovery code"],
                h.p[
                    "Keep this code somewhere private. It restores your seats if you lose this browser. It is shown only once."
                ],
                h.code(id="recovery-code")[recovery],
                h.p["Using a recovery code signs out every other browser and replaces the code."],
            ]
            if recovery
            else None,
            h.a(class_="button primary", href="/")["Continue to your tables"]
            if authenticated
            else None,
            form(
                "/identity",
                csrf,
                "Create player",
                h.label[
                    "Display name",
                    h.input(
                        name="display_name", maxlength="40", required=True, autocomplete="nickname"
                    ),
                ],
            )
            if not authenticated
            else None,
            form(
                "/recover",
                csrf,
                "Recover player",
                h.label[
                    "Recovery code",
                    h.input(
                        name="recovery_code", required=True, autocomplete="off", type="password"
                    ),
                ],
            )
            if not authenticated
            else None,
            form("/logout", csrf, "Sign out") if authenticated else None,
        ],
    )


def setup_fields(themes: tuple[Theme, ...], table: TableView | None = None) -> h.Element:
    count = len(table.seats) if table else 2
    return h.div[
        h.label[
            "Players",
            h.select(name="players", id="players")[
                [h.option(value=str(n), selected=n == count)[str(n)] for n in (2, 3, 4)]
            ],
        ],
        h.p[
            "You occupy the first seat. Invite friends or choose a computer opponent for each remaining seat."
        ],
        [
            h.label(data_opponent=str(index))[
                f"Seat {index + 1}",
                h.select(name=f"controller{index}")[
                    [
                        h.option(
                            value=value,
                            selected=value
                            == (
                                table.seats[index].controller
                                if table and index < count
                                else "human"
                            ),
                        )["Invited human" if value == "human" else f"{value.capitalize()} computer"]
                        for value in ("human", *STRATEGIES)
                    ]
                ],
            ]
            for index in (1, 2, 3)
        ],
        h.label[
            "Supply",
            h.select(name="supply", id="supply-mode")[
                [
                    h.option(value=value, selected=value == ("manual" if table else "starter"))[
                        label
                    ]
                    for value, label in (
                        ("starter", "First steps"),
                        ("random", "Surprise me"),
                        ("manual", "Choose ten cards"),
                    )
                ]
            ],
        ],
        h.fieldset(id="manual-supply")[
            h.legend["Choose ten different cards"],
            [
                h.label[
                    h.input(
                        type="checkbox",
                        name="kingdom",
                        value=card,
                        checked=bool(table and card in table.kingdom),
                    ),
                    themes[0].cards[card].name,
                ]
                for card in KINGDOM_IDS
            ],
        ],
    ]


def home(tables: tuple[TableView, ...], csrf: str, themes: tuple[Theme, ...]) -> h.Element:
    return hosted_page(
        "Your tables",
        h.main(id="main", class_="home")[
            h.h1["A table with friends"],
            h.a(href="/account")["Your player and sign out"],
            h.div(class_="home-columns")[
                h.section(class_="panel")[
                    h.h2["Set a private table"],
                    form("/games", csrf, "Create table", setup_fields(themes)),
                ],
                h.section(class_="panel")[
                    h.h2["Your tables"],
                    h.ul[
                        [
                            h.li[
                                h.a(href=f"/games/{table.game_id}")[
                                    " · ".join(
                                        seat.display_name for seat in table.seats if seat.occupied
                                    ),
                                    f" — {table.status}",
                                ]
                            ]
                            for table in tables
                        ]
                    ]
                    if tables
                    else h.p["Your invitations and saved tables will appear here."],
                ],
            ],
        ],
    )


def table_content(
    table: TableView, csrf: str, themes: tuple[Theme, ...], error: str | None = None
) -> h.Element:
    path = f"/games/{table.game_id}"
    revision = hidden("lobby_revision", table.lobby_revision)
    theme = next((theme for theme in themes if theme.id == table.theme_id), themes[0])
    waiting = (
        table.seats[table.pending_player].display_name if table.pending_player is not None else None
    )
    return h.div(
        id="table",
        data_hosted="true",
        data_url=path,
        data_revision=str(table.revision),
        data_lobby_revision=str(table.lobby_revision),
        data_preference_version=str(table.preference_version),
    )[
        h.p(class_="notice error", role="alert")[error] if error else None,
        h.main(id="main", class_="home")[
            h.h1["This table was cancelled"],
            h.p["No winner was recorded."],
            h.a(href="/")["Your tables"],
        ]
        if table.status == "cancelled"
        else board(
            table.view,
            BoardContext(
                table.game_id,
                csrf,
                theme,
                themes,
                hosted=True,
                waiting_for=waiting,
                bot_paused=table.bot_paused is not None,
                preference_version=table.preference_version,
            ),
        )
        if table.view
        else h.main(id="main", class_="home")[
            h.h1["Gather around"],
            h.p[
                "Every human must be ready before the host starts. Changing setup clears everyone's readiness."
            ],
            h.ul(class_="panel")[
                [
                    h.li[
                        f"Seat {seat.seat + 1}: {seat.display_name or 'Waiting for an invitation'}",
                        " · Ready"
                        if seat.ready
                        else " · Not ready"
                        if seat.controller == "human"
                        else " · Computer",
                        form(
                            f"{path}/invite",
                            csrf,
                            f"Invite seat {seat.seat + 1}",
                            hidden("seat", seat.seat),
                        )
                        if table.host and seat.controller == "human" and not seat.occupied
                        else None,
                        form(
                            f"{path}/revoke-invite",
                            csrf,
                            "Revoke invitation",
                            hidden("seat", seat.seat),
                        )
                        if table.host and seat.controller == "human" and not seat.occupied
                        else None,
                        form(
                            f"{path}/remove",
                            csrf,
                            "Remove player",
                            hidden("seat", seat.seat),
                            revision,
                        )
                        if table.host
                        and seat.controller == "human"
                        and seat.occupied
                        and seat.seat != table.seat
                        else None,
                    ]
                    for seat in table.seats
                ]
            ],
            form(
                f"{path}/ready",
                csrf,
                "Not ready" if table.seats[table.seat].ready else "I'm ready",
                revision,
                hidden("ready", "false" if table.seats[table.seat].ready else "true"),
            ),
            form(f"{path}/start", csrf, "Start game", revision) if table.host else None,
            h.details[
                h.summary["Change table setup"],
                form(
                    f"{path}/configure", csrf, "Save setup", revision, setup_fields(themes, table)
                ),
            ]
            if table.host
            else None,
        ],
        h.details(class_="home")[
            h.summary["Table controls"], form(f"{path}/cancel", csrf, "Cancel table")
        ]
        if table.host and table.status not in {"finished", "cancelled"}
        else None,
    ]


def invitation(csrf: str, invitation_id: str, authenticated: bool) -> h.Element:
    return hosted_page(
        "Join a table",
        h.main(id="main", class_="home")[
            h.h1["You're invited"],
            h.p[
                "Join with your player, or create a player below. The invitation is used only when you choose Join table."
            ],
            h.form(action=f"/join/{invitation_id}", method="post", id="join-form")[
                csrf_input(csrf),
                hidden("secret", ""),
                h.label["Display name", h.input(name="display_name", maxlength="40", required=True)]
                if not authenticated
                else None,
                h.button(type="submit", class_="primary")["Join table"],
            ],
            h.p(id="invite-error", role="alert"),
            h.noscript["JavaScript is needed to read the private invitation from this link."],
        ],
    )
