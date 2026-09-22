"""Validated, data-only presentation packs. Rules never read these manifests."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

STATIC_ROOT = Path(__file__).resolve().parent.parent / "static"
THEME_ROOT = STATIC_ROOT / "themes"


class CardPresentation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=1000)
    image: str
    image_alt: str = Field(min_length=1)


class ThemeTokens(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    background: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    surface: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    ink: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    muted: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    gold: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class Theme(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1, le=1)
    id: str = Field(pattern=r"^[a-z][a-z0-9-]+$")
    name: str
    tagline: str
    tokens: ThemeTokens
    terms: dict[str, str]
    cards: dict[str, CardPresentation]

    def term(self, key: str) -> str:
        return self.terms.get(key, key.replace("_", " ").capitalize())

    @property
    def style(self) -> str:
        return ";".join(
            f"--{key}:{value}" for key, value in self.tokens.model_dump().items()
        )


def load_theme(path: Path, required_ids: frozenset[str]) -> Theme:
    """Fail before activation if a pack is incomplete or references unsafe assets."""
    try:
        theme = Theme.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise ValueError(f"Cannot load theme {path.name}: {exc}") from exc
    if set(theme.cards) != required_ids:
        raise ValueError("Theme card coverage does not match the game's card catalog")
    required_terms = {"actions", "buys", "coins", "points", "supply", "hand", "played"}
    if not required_terms <= theme.terms.keys():
        raise ValueError("Theme is missing required terminology")
    for card in theme.cards.values():
        asset = (STATIC_ROOT / card.image).resolve()
        if not asset.is_relative_to(STATIC_ROOT.resolve()) or not asset.is_file():
            raise ValueError(f"Theme asset is missing or outside the asset directory: {card.image}")
        if asset.suffix not in {".svg", ".png", ".jpg", ".webp"}:
            raise ValueError("Unsupported theme image type")
    return theme


def load_themes(required_ids: frozenset[str]) -> dict[str, Theme]:
    themes: dict[str, Theme] = {}
    for path in sorted(THEME_ROOT.glob("*.json")):
        theme = load_theme(path, required_ids)
        if theme.id in themes:
            raise ValueError(f"Duplicate theme ID: {theme.id}")
        themes[theme.id] = theme
    if "neutral" not in themes:
        raise ValueError("The neutral theme is required")
    return themes
