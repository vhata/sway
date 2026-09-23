"""HTML components consume filtered views, never authoritative game state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import htpy as h

from sway.engine.catalog import CATALOG, KINGDOM_IDS, OFFICIAL_NAMES
from sway.engine.models import Card, Decision, Event, Option, PlayerView
from sway.presentation.themes import Theme

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True)
class SavedGame:
    game_id: str
    revision: int
    theme_id: str
    status: str
    updated_at: str
    player_names: tuple[str, ...]


@dataclass(frozen=True)
class BoardContext:
    game_id: str
    csrf: str
    theme: Theme
    themes: tuple[Theme, ...]
    error: str | None = None
    pause_bots: bool = False
    developer_terminology: bool = False


def page(title: str, content: h.Node) -> h.Element:
    return h.html(lang="en")[
        h.head[
            h.meta(charset="utf-8"),
            h.meta(name="viewport", content="width=device-width, initial-scale=1"),
            h.meta(name="color-scheme", content="light dark"),
            h.meta(name="htmx-config", content='{"allowEval":false,"allowScriptTags":false}'),
            h.title[f"{title} · Sway"],
            h.link(rel="stylesheet", href="/static/style.css"),
            h.script(src="/static/vendor/htmx-2.0.10.min.js", defer=True),
            h.script(src="/static/app.js", defer=True),
        ],
        h.body[
            h.a(class_="skip-link", href="#main")["Skip to content"],
            h.header(class_="site-header")[
                h.a(class_="wordmark", href="/", aria_label="Sway home")["sway", h.span["✦"]],
                h.span(class_="header-note")["A little strategy. A world of possibilities."],
                h.a(class_="quiet-link", href="/")["Your games"],
            ],
            content,
            h.footer(class_="site-footer")["Made for thoughtful turns."],
        ],
    ]


def csrf_input(token: str) -> h.VoidElement:
    return h.input(type="hidden", name="csrf", value=token)


def home(
    games: Sequence[SavedGame],
    themes: tuple[Theme, ...],
    csrf: str,
    error: str | None = None,
    *,
    developer_terminology: bool = False,
) -> h.Element:
    common_ground = next((theme for theme in themes if theme.id == "common-ground"), themes[0])
    return page(
        "Your table awaits",
        h.main(id="main", class_="home", style=common_ground.style)[
            h.section(class_="welcome")[
                h.p(class_="eyebrow")["A game of growing possibilities"],
                h.h1["Start small.", h.br, h.em["Build your advantage."]],
                h.p(class_="lede")[
                    "Shape your deck, find a rhythm, and make every turn count. Your next table is ready when you are."
                ],
            ],
            h.div(class_="home-columns")[
                h.section(class_="panel setup")[
                    h.h2["Set your table"],
                    h.p["One player. A few worthy opponents. Plenty of ways to win."],
                    h.p(class_="notice error", role="alert")[error] if error else None,
                    h.form(action="/games", method="post", id="setup-form")[
                        csrf_input(csrf),
                        h.div(class_="form-grid")[
                            h.label[
                                "Players",
                                h.select(name="players", id="players")[
                                    h.option(value="2")["2 — you + one opponent"],
                                    h.option(value="3")["3 — you + two opponents"],
                                    h.option(value="4")["4 — you + three opponents"],
                                ],
                            ],
                            h.label[
                                "Table theme",
                                h.select(name="theme")[
                                    [h.option(value=theme.id)[theme.name] for theme in themes]
                                ],
                            ],
                            h.label[
                                "Game seed",
                                h.input(
                                    type="number",
                                    name="seed",
                                    value="42",
                                    min="0",
                                    max=str(2**63 - 1),
                                ),
                            ],
                            h.label[
                                "Supply",
                                h.select(name="supply", id="supply-mode")[
                                    h.option(value="starter")["First steps — a balanced selection"],
                                    h.option(value="random")["Surprise me — 10 random cards"],
                                    h.option(value="manual")["Choose my own 10 cards"],
                                ],
                            ],
                        ],
                        h.fieldset(class_="opponents")[
                            h.legend["Your opponents"],
                            [
                                h.label(data_opponent=str(index))[
                                    f"Opponent {index}",
                                    h.select(name=f"strategy{index}")[
                                        h.option(value="economy")["Economy — builds buying power"],
                                        h.option(value="engine", selected=index == 2)[
                                            "Engine — combines useful actions"
                                        ],
                                        h.option(value="attack", selected=index == 3)[
                                            "Attack — disrupts your plans"
                                        ],
                                    ],
                                ]
                                for index in range(1, 4)
                            ],
                        ],
                        h.fieldset(id="manual-supply", class_="manual-supply")[
                            h.legend["Choose exactly 10 cards"],
                            h.div(class_="manual-grid")[
                                [
                                    h.label[
                                        h.input(type="checkbox", name="kingdom", value=card_id),
                                        common_ground.cards[card_id].name,
                                        h.small[f" · {CATALOG[card_id].cost}"],
                                        original_name(card_id, developer_terminology),
                                    ]
                                    for card_id in KINGDOM_IDS
                                ]
                            ],
                        ],
                        h.button(type="submit", class_="primary")[
                            "Begin a game", h.span(aria_hidden="true")[" ↗"]
                        ],
                        h.p(class_="fine-print")[
                            "Every turn is saved automatically. Come back whenever you like."
                        ],
                    ],
                ],
                h.section(class_="saved-games")[
                    h.p(class_="eyebrow")["Pick up where you left off"],
                    h.h2["Your tables"],
                    [
                        h.a(class_="saved-game", href=f"/games/{game.game_id}")[
                            h.div[
                                h.strong[" · ".join(game.player_names)],
                                h.small[game.updated_at[:16].replace("T", " ")],
                            ],
                            h.span(class_="pill")[
                                "Finished" if game.status == "finished" else "Resume →"
                            ],
                        ]
                        for game in games
                    ]
                    if games
                    else h.div(class_="empty-state")[
                        h.span(class_="empty-symbol", aria_hidden="true")["◇"],
                        h.p["A fresh start."],
                        h.small["Your saved games will live here."],
                    ],
                    h.aside(class_="table-tip")[
                        h.h3["A good first move"],
                        h.p[
                            "Coins help you acquire cards. Actions make your turns stronger. Points decide who wins — but point cards can slow your deck down."
                        ],
                    ],
                ],
            ],
        ],
    )


def original_name(card_id: str | None, enabled: bool) -> h.Element | None:
    if not enabled or card_id is None:
        return None
    return h.small(class_="original-name")[f"Original: {OFFICIAL_NAMES[card_id]}"]


def card_face(
    card_id: str,
    theme: Theme,
    *,
    count: int | None = None,
    compact: bool = False,
    developer_terminology: bool = False,
) -> h.Element:
    card = theme.cards[card_id]
    definition = CATALOG[card_id]
    category = (
        "attack"
        if "attack" in definition.types
        else "reaction"
        if "reaction" in definition.types
        else sorted(definition.types)[0]
    )
    return h.div(class_=f"card-face card-{category}" + (" compact" if compact else ""))[
        h.div(class_="card-top")[
            h.div(class_="card-title")[
                h.strong[card.name], original_name(card_id, developer_terminology)
            ]
            if developer_terminology
            else h.strong[card.name],
            h.span(class_="cost", title="Cost", aria_label=f"Costs {definition.cost}")[
                str(definition.cost)
            ],
        ],
        h.img(
            src=f"/static/{card.image}", alt=card.image_alt, width="72", height="72", loading="lazy"
        ),
        h.p(class_="card-description")[card.description],
        h.div(class_="card-bottom")[
            h.small[" · ".join(sorted(definition.types))],
            h.span(class_="pile-count", aria_label=f"{count} remaining")[str(count)]
            if count is not None
            else None,
        ],
    ]


MENU_LABELS = {
    "end-actions": "Finish actions",
    "play-treasures": "Play all treasures",
    "end-turn": "End your turn",
    "yes": "Yes",
    "no": "No",
    "reveal": "Reveal protection",
    "decline": "Allow the attack",
}
PROMPTS = {
    "action": "Choose an action to play",
    "buy": "Make your next move",
    "trash": "Choose cards to scrap",
    "discard": "Choose cards to discard",
    "gain": "Choose a card to take",
    "topdeck": "Choose a card to put on your deck",
    "reaction": "Protect yourself from this attack?",
    "order": "Arrange these cards, top card first",
    "cellar": "Discard cards, then draw the same number",
    "chapel": "Scrap up to four cards",
    "harbinger": "Return a discarded card to your deck?",
    "mine": "Choose a Treasure to upgrade",
    "moneylender": "Scrap the smallest Treasure for three coins?",
    "poacher": "Discard for the empty supply piles",
    "remodel": "Choose a card to replace",
    "throne": "Choose an Action to play twice",
    "vassal": "Play the discarded Action?",
    "gain_hand": "Choose a card to take into your hand",
    "bandit": "Choose a revealed Treasure to scrap",
    "bureaucrat": "Return a Victory card to your deck",
    "militia": "Discard down to three cards",
    "library": "Keep this Action card?",
    "sentry_trash": "Scrap any of the inspected cards",
    "sentry_discard": "Discard any remaining inspected cards",
    "sentry_order": "Arrange the remaining cards, top card first",
}


def option_label(option: Option, theme: Theme) -> str:
    if option.card_id is not None:
        return theme.cards[option.card_id].name
    return MENU_LABELS.get(option.id, option.id.replace("-", " ").capitalize())


def choice_form(decision: Decision, view: PlayerView, ctx: BoardContext) -> h.Element:
    path = f"/games/{ctx.game_id}/decisions"
    ordered = decision.ordered or decision.kind == "order"
    full_order = ordered and decision.minimum == decision.maximum == len(decision.options)
    cards: list[h.Node] = []
    for index, option in enumerate(decision.options):
        choice_id = f"choice-{decision.id}-{index}"
        if ordered:
            cards.append(
                h.li(class_="order-item", data_option=option.id)[
                    h.input(
                        type="hidden" if full_order else "checkbox",
                        name="choices",
                        value=option.id,
                        id=choice_id,
                    ),
                    h.label(for_=choice_id)[
                        option_label(option, ctx.theme),
                        original_name(option.card_id, ctx.developer_terminology),
                    ]
                    if not full_order
                    else h.span[
                        option_label(option, ctx.theme),
                        original_name(option.card_id, ctx.developer_terminology),
                    ],
                    h.button(
                        type="button",
                        data_move="up",
                        aria_label=f"Move {option_label(option, ctx.theme)} earlier",
                    )["↑"],
                    h.button(
                        type="button",
                        data_move="down",
                        aria_label=f"Move {option_label(option, ctx.theme)} later",
                    )["↓"],
                ]
            )
        else:
            cards.append(
                h.label(
                    class_="choice" + (" text-choice" if option.card_id is None else ""),
                    for_=choice_id,
                )[
                    h.input(
                        type="radio" if decision.maximum == 1 else "checkbox",
                        name="choices",
                        value=option.id,
                        id=choice_id,
                    ),
                    h.span(class_="choice-caption")[
                        "Play from hand" if option.instance_id else "Buy from supply"
                    ]
                    if decision.prompt == "buy" and option.card_id
                    else None,
                    card_face(
                        option.card_id,
                        ctx.theme,
                        compact=True,
                        developer_terminology=ctx.developer_terminology,
                    )
                    if option.card_id
                    else h.span[option_label(option, ctx.theme)],
                ]
            )
    return h.form(
        action=path,
        method="post",
        hx_post=path,
        hx_target="#board",
        hx_swap="outerHTML",
        id="decision-form",
        data_decision=decision.id,
        data_minimum=str(decision.minimum),
        data_maximum=str(decision.maximum),
        data_ordered=str(full_order).lower(),
    )[
        csrf_input(ctx.csrf),
        h.input(type="hidden", name="revision", value=str(view.revision)),
        h.input(type="hidden", name="decision", value=decision.id),
        h.fieldset[
            h.legend(id="decision-heading", tabindex="-1")[
                PROMPTS.get(
                    decision.prompt,
                    decision.prompt.replace("_", " ").replace("-", " ").capitalize(),
                ).replace("coins", ctx.theme.term("coins").lower())
            ],
            h.p(class_="selection-hint")[
                "Use the arrows to choose the order."
                if full_order
                else f"Choose {decision.minimum}"
                + (f"–{decision.maximum}" if decision.minimum != decision.maximum else "")
                + " option"
                + ("s" if decision.maximum != 1 else "")
                + ("; use the arrows to order your selected cards." if ordered else ".")
            ],
            h.ol(class_="ordered-choices")[cards] if ordered else h.div(class_="choices")[cards],
        ],
        h.div(class_="decision-actions")[
            h.button(type="submit", class_="primary", id="confirm-choice")["Confirm choice"],
            h.button(type="reset", class_="secondary")["Clear selection"]
            if not full_order
            else None,
            h.span(class_="selection-status", aria_live="polite"),
        ],
    ]


def event_text(event: Event, view: PlayerView, theme: Theme) -> str:
    player = (
        view.players[event.player].name if 0 <= event.player < len(view.players) else "The table"
    )
    names = ", ".join(theme.cards[card.definition].name for card in event.cards)
    verbs = {
        "play": "played",
        "played": "played",
        "gain": "gained",
        "gained": "gained",
        "buy": "bought",
        "bought": "bought",
        "trash": "scrapped",
        "trashed": "scrapped",
        "discard": "discarded",
        "discarded": "discarded",
        "discard_top": "discarded (top card)",
        "block": "blocked the attack with",
        "set_aside": "set aside",
        "reveal": "revealed",
        "revealed": "revealed",
        "draw": "drew",
        "drew": "drew",
        "topdeck": "returned to their deck",
    }
    if event.kind in verbs:
        detail = names or f"{event.amount} card" + ("s" if event.amount != 1 else "")
        return f"{player} {verbs[event.kind]} {detail}."
    if event.kind in {"turn", "turn_start"}:
        return f"{player} began a turn."
    if event.kind == "shuffle":
        return f"{player} shuffled their discard pile."
    if event.kind in {"finished", "game_end", "game_over"}:
        return "The game has finished."
    return f"{player}: {event.kind.replace('_', ' ')}" + (f" — {names}" if names else "") + "."


def card_row(
    cards: tuple[Card, ...], theme: Theme, *, developer_terminology: bool = False
) -> h.Element:
    return h.div(class_="card-row")[
        [
            card_face(
                card.definition,
                theme,
                compact=True,
                developer_terminology=developer_terminology,
            )
            for card in cards
        ]
    ]


def class_looked(
    cards: tuple[Card, ...], theme: Theme, *, developer_terminology: bool = False
) -> h.Element:
    return h.div(class_="looked-cards")[
        h.h3["Cards you are inspecting"],
        card_row(cards, theme, developer_terminology=developer_terminology),
    ]


def board(view: PlayerView, ctx: BoardContext) -> h.Element:
    theme = ctx.theme
    own = view.players[view.player]
    bot_active = view.phase != "finished" and view.decision_owner != view.player
    return h.main(
        id="board",
        class_="board",
        style=theme.style,
        data_theme=theme.id,
        data_revision=str(view.revision),
    )[
        h.div(id="main", class_="table-heading")[
            h.div[h.p(class_="eyebrow")[theme.name], h.h1["Your table"], h.p[theme.tagline]],
            h.form(
                action=f"/games/{ctx.game_id}/theme",
                method="post",
                hx_post=f"/games/{ctx.game_id}/theme",
                hx_target="#board",
                hx_swap="outerHTML",
                class_="theme-control",
            )[
                csrf_input(ctx.csrf),
                h.label[
                    "Change the scenery",
                    h.select(name="theme", id="theme-select", aria_label="Theme")[
                        [
                            h.option(value=pack.id, selected=pack.id == theme.id)[pack.name]
                            for pack in ctx.themes
                        ]
                    ],
                ],
                h.button(type="submit", class_="secondary")["Apply theme"],
            ],
        ],
        h.p(class_="notice error", role="alert")[ctx.error] if ctx.error else None,
        h.div(class_="table-status")[
            h.span(class_="turn-label")[
                f"Turn {view.turn} · {view.players[view.active_player].name}"
            ],
            h.div(class_="counters")[
                [
                    h.div(class_="counter")[h.strong[str(value)], h.span[theme.term(key)]]
                    for key, value in [
                        ("actions", view.actions),
                        ("buys", view.buys),
                        ("coins", view.coins),
                    ]
                ]
            ],
        ],
        h.section(class_="opponent-row", aria_label="Players")[
            [
                h.article(class_="opponent" + (" active" if index == view.active_player else ""))[
                    h.span(class_="avatar", aria_hidden="true")[str(index + 1)],
                    h.div[
                        h.h2[player.name],
                        h.p[
                            f"{player.hand_count} in hand"
                            + (
                                f" · {player.deck_count} in deck"
                                if player.deck_count is not None
                                else ""
                            )
                        ],
                    ],
                    h.details[
                        h.summary["Public cards"],
                        h.h3["In play"],
                        card_row(
                            player.in_play, theme, developer_terminology=ctx.developer_terminology
                        ),
                        h.h3["Top discard"],
                        card_row(
                            player.discard, theme, developer_terminology=ctx.developer_terminology
                        ),
                        h.h3["Revealed"],
                        card_row(
                            player.revealed, theme, developer_terminology=ctx.developer_terminology
                        ),
                        h.h3["Set aside"],
                        card_row(
                            player.set_aside, theme, developer_terminology=ctx.developer_terminology
                        ),
                    ],
                ]
                for index, player in enumerate(view.players)
            ]
        ],
        h.section(class_="decision-panel panel", aria_label="Current decision")[
            h.div[class_looked(view.looked, theme, developer_terminology=ctx.developer_terminology)]
            if view.looked
            else None,
            h.div(class_="finished")[
                h.p(class_="eyebrow")["Every choice counted"],
                h.h2[
                    " & ".join(view.players[index].name for index in view.winners)
                    + " win"
                    + ("s" if len(view.winners) == 1 else "")
                    + "!"
                ],
                h.ul[
                    [
                        h.li[
                            f"{player.name}: {view.scores[index]} {theme.term('points').lower()} · {player.turns} turns"
                        ]
                        for index, player in enumerate(view.players)
                    ]
                ],
                h.a(class_="button primary", href="/")["Set another table"],
            ]
            if view.phase == "finished"
            else choice_form(view.pending, view, ctx)
            if view.pending
            else h.form(
                action=f"/games/{ctx.game_id}/advance",
                method="post",
                hx_post=f"/games/{ctx.game_id}/advance",
                hx_trigger="load delay:250ms" if bot_active and not ctx.pause_bots else "submit",
                hx_target="#board",
                hx_swap="outerHTML",
                id="bot-progress",
            )[
                csrf_input(ctx.csrf),
                h.input(type="hidden", name="revision", value=str(view.revision)),
                h.h2["The table is moving…"],
                h.p["Your opponents are considering their next move. Your turn will appear here."],
                h.button(type="submit", class_="secondary")["Continue opponents"],
            ],
        ],
        h.div(class_="table-columns")[
            h.div(class_="main-table")[
                h.section(class_="hand-section")[
                    h.h2[theme.term("hand")],
                    card_row(view.hand, theme, developer_terminology=ctx.developer_terminology),
                    h.p(class_="fine-print")[f"{own.deck_count} in your deck"],
                ],
                h.section(class_="played-section")[
                    h.h2[theme.term("played")],
                    card_row(own.in_play, theme, developer_terminology=ctx.developer_terminology)
                    if own.in_play
                    else h.p(class_="empty-line")["Your played cards will gather here."],
                ],
                h.section(class_="supply-section")[
                    h.h2[theme.term("supply")],
                    h.div(class_="supply-grid")[
                        [
                            card_face(
                                card_id,
                                theme,
                                count=count,
                                developer_terminology=ctx.developer_terminology,
                            )
                            for card_id, count in sorted(
                                view.supply.items(),
                                key=lambda item: (
                                    not item[0].startswith("k"),
                                    CATALOG[item[0]].cost,
                                    item[0],
                                ),
                            )
                        ]
                    ],
                ],
            ],
            h.aside(class_="history panel")[
                h.h2["Around the table"],
                h.p(class_="fine-print")["Latest moves first"],
                h.ol[
                    [h.li[event_text(event, view, theme)] for event in reversed(view.events[-80:])]
                ],
                h.details[
                    h.summary[f"Scrapped cards ({len(view.trash)})"],
                    card_row(view.trash, theme, developer_terminology=ctx.developer_terminology),
                ],
            ],
        ],
        h.p(class_="save-status", role="status")[
            "All moves saved · You can leave and return at any time."
        ],
    ]
