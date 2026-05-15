"""Color parsing and generation helpers."""

from __future__ import annotations

import colorsys
from collections.abc import Sequence

ANSI_COLORS: dict[str, str] = {
    "black": "\033[30m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "gray": "\033[90m",
    "grey": "\033[90m",
    "bright_red": "\033[91m",
    "bright_green": "\033[92m",
    "bright_yellow": "\033[93m",
    "bright_blue": "\033[94m",
    "bright_magenta": "\033[95m",
    "bright_cyan": "\033[96m",
    "bright_white": "\033[97m",
}

RGB_COLORS: dict[str, tuple[int, int, int]] = {
    "black": (0, 0, 0),
    "red": (204, 0, 0),
    "green": (0, 170, 0),
    "yellow": (234, 179, 8),
    "blue": (37, 99, 235),
    "magenta": (192, 38, 211),
    "cyan": (8, 145, 178),
    "white": (245, 245, 245),
    "gray": (107, 114, 128),
    "grey": (107, 114, 128),
    "orange": (249, 115, 22),
    "purple": (126, 34, 206),
    "pink": (219, 39, 119),
    "lime": (101, 163, 13),
    "teal": (13, 148, 136),
}

DEFAULT_COLORS: tuple[str, str] = ("#000000", "#CC0000")
ANSI_RESET = "\033[0m"


def generated_rgb(index: int, total: int) -> tuple[int, int, int]:
    """Generate a stable, reasonably distinct RGB color for a team index."""
    hue = index / max(total, 1)
    red, green, blue = colorsys.hsv_to_rgb(hue, 0.72, 0.86)
    return round(red * 255), round(green * 255), round(blue * 255)


def parse_rgb(raw_color: str) -> tuple[int, int, int]:
    """Parse a named color, #RGB, #RRGGBB, RGB, or RRGGBB color."""
    normalized = raw_color.strip()
    lower = normalized.lower().replace("-", "_")

    if lower in RGB_COLORS:
        return RGB_COLORS[lower]

    if normalized.startswith("#"):
        normalized = normalized[1:]

    if len(normalized) == 3:
        normalized = "".join(character * 2 for character in normalized)

    if len(normalized) != 6:
        raise ValueError(f"Invalid color {raw_color!r}. Use a known name, #RGB, or #RRGGBB.")

    try:
        red = int(normalized[0:2], 16)
        green = int(normalized[2:4], 16)
        blue = int(normalized[4:6], 16)
    except ValueError as error:
        raise ValueError(f"Invalid color {raw_color!r}. Use a known name, #RGB, or #RRGGBB.") from error

    return red, green, blue


def flatten_color_args(raw_colors: Sequence[Sequence[str]] | None) -> list[str]:
    """Flatten repeated --color groups while preserving CLI order."""
    if not raw_colors:
        return []

    return [color for group in raw_colors for color in group]


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Return #RRGGBB for an RGB tuple."""
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"
