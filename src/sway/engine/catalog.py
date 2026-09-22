"""Mechanical card definitions; names and descriptive text belong to themes.

The developer-facing mapping is kept here for rule auditing and terminology docs.
"""

from sway.engine.models import CardDefinition

OFFICIAL_NAMES: dict[str, str] = {
    "k01": "Artisan",
    "k02": "Bandit",
    "k03": "Bureaucrat",
    "k04": "Cellar",
    "k05": "Chapel",
    "k06": "Council Room",
    "k07": "Festival",
    "k08": "Gardens",
    "k09": "Harbinger",
    "k10": "Laboratory",
    "k11": "Library",
    "k12": "Market",
    "k13": "Merchant",
    "k14": "Militia",
    "k15": "Mine",
    "k16": "Moat",
    "k17": "Moneylender",
    "k18": "Poacher",
    "k19": "Remodel",
    "k20": "Sentry",
    "k21": "Smithy",
    "k22": "Throne Room",
    "k23": "Vassal",
    "k24": "Village",
    "k25": "Witch",
    "k26": "Workshop",
    "treasure1": "Copper",
    "treasure2": "Silver",
    "treasure3": "Gold",
    "victory1": "Estate",
    "victory2": "Duchy",
    "victory3": "Province",
    "curse": "Curse",
}

_COSTS = (6, 5, 4, 2, 2, 5, 5, 4, 3, 5, 5, 5, 3, 4, 5, 2, 4, 4, 4, 5, 4, 4, 3, 3, 5, 3)
KINGDOM_IDS = tuple(f"k{number:02}" for number in range(1, 27))
CATALOG: dict[str, CardDefinition] = {
    key: CardDefinition(
        key,
        cost,
        frozenset(
            {"victory"}
            if key == "k08"
            else {"action", "attack"}
            if key in {"k02", "k03", "k14", "k25"}
            else {"action", "reaction"}
            if key == "k16"
            else {"action"}
        ),
    )
    for key, cost in zip(KINGDOM_IDS, _COSTS, strict=True)
}
CATALOG.update(
    {
        "treasure1": CardDefinition("treasure1", 0, frozenset({"treasure"}), coins=1),
        "treasure2": CardDefinition("treasure2", 3, frozenset({"treasure"}), coins=2),
        "treasure3": CardDefinition("treasure3", 6, frozenset({"treasure"}), coins=3),
        "victory1": CardDefinition("victory1", 2, frozenset({"victory"}), points=1),
        "victory2": CardDefinition("victory2", 5, frozenset({"victory"}), points=3),
        "victory3": CardDefinition("victory3", 8, frozenset({"victory"}), points=6),
        "curse": CardDefinition("curse", 0, frozenset({"curse"}), points=-1),
    }
)
