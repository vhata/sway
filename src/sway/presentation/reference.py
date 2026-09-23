"""Read-only developer catalogue using the same card faces as the game."""

import htpy as h

from sway.engine.catalog import CATALOG, KINGDOM_IDS
from sway.presentation.components import card_face, page
from sway.presentation.themes import Theme


def card_reference(theme: Theme, themes: tuple[Theme, ...]) -> h.Element:
    groups = (
        ("Basic cards", set(CATALOG) - set(KINGDOM_IDS)),
        ("Kingdom cards", set(KINGDOM_IDS)),
    )
    return page(
        "Developer card catalogue",
        h.main(id="main", class_="home", style=theme.style)[
            h.p(class_="eyebrow")["Developer reference"],
            h.h1["Card catalogue"],
            h.p[
                "Every card in its normal theme, with original names for reference. "
                "Changing this view does not affect your saved tables."
            ],
            h.form(action="/developer/cards", method="get", class_="theme-picker")[
                h.label[
                    "Theme",
                    h.select(name="theme")[
                        [
                            h.option(value=pack.id, selected=pack.id == theme.id)[pack.name]
                            for pack in themes
                        ]
                    ],
                ],
                h.button(type="submit")["Show cards"],
            ],
            [
                h.section(class_="panel")[
                    h.h2[title],
                    h.div(class_="supply-grid")[
                        [
                            h.div(data_card_id=card_id)[
                                card_face(card_id, theme, developer_terminology=True)
                            ]
                            for card_id in sorted(
                                card_ids,
                                key=lambda identifier: (
                                    CATALOG[identifier].cost,
                                    theme.cards[identifier].name,
                                ),
                            )
                        ]
                    ],
                ]
                for title, card_ids in groups
            ],
        ],
    )
