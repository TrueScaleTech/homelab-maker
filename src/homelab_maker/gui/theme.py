"""Every colour the application uses, in one place.

This module has no Qt in it: colours are plain ``#rrggbb`` strings, so the contrast between
them can be tested for both appearances. Widgets never write a colour of their own.
"""

from dataclasses import dataclass
from typing import Literal

Scheme = Literal["system", "light", "dark"]


@dataclass(frozen=True, slots=True)
class Tokens:
    name: str
    background: str
    grid_minor: str
    grid_major: str
    card: str
    card_border: str
    text: str
    text_muted: str
    accent: str
    danger: str
    link: str
    # Colours for zones, cycled in order, drawn with zone_alpha (0-255) over the canvas.
    # Labels use text_muted over the result.
    zones: tuple[str, ...]
    zone_alpha: int


LIGHT = Tokens(
    name="light",
    background="#f6f7f9",
    grid_minor="#e6e9ee",
    grid_major="#d3d8e0",
    card="#ffffff",
    card_border="#c3cad5",
    text="#1b2230",
    text_muted="#4a5568",
    accent="#2563eb",
    danger="#c0262d",
    link="#5b6678",
    zones=("#2563eb", "#16a34a", "#d97706", "#9333ea"),
    zone_alpha=34,
)

DARK = Tokens(
    name="dark",
    background="#14171d",
    grid_minor="#1d222b",
    grid_major="#2a313d",
    card="#1e232c",
    card_border="#3a4352",
    text="#e8ecf2",
    text_muted="#a9b4c4",
    accent="#6ea0ff",
    danger="#ff7b80",
    link="#8b97aa",
    zones=("#6ea0ff", "#4ade80", "#fbbf24", "#c084fc"),
    zone_alpha=38,
)


def choose(scheme: Scheme, system_is_dark: bool) -> Tokens:
    """The tokens for a preference. ``system`` follows the operating system."""
    if scheme == "light":
        return LIGHT
    if scheme == "dark":
        return DARK
    return DARK if system_is_dark else LIGHT


def _channel(value: int) -> float:
    s = value / 255
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def luminance(colour: str) -> float:
    """Relative luminance of ``#rrggbb`` as WCAG defines it."""
    red, green, blue = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def contrast(first: str, second: str) -> float:
    """WCAG contrast ratio between two ``#rrggbb`` colours, from 1 to 21."""
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)
