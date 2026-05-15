#!/usr/bin/env python3
"""Greedy knight placement on an infinite spiral-numbered square grid.

Spiral convention:
    0 = (0, 0)
    1 = (1, 0)
    2 = (1, 1)
    3 = (0, 1)

Then the numbering continues counterclockwise around each square ring.

Rules:
    On each turn, the active team places one knight on the lowest-numbered
    unoccupied square that is not currently attacked by any opposing team's
    knights. Attacks from the active team's own knights do not matter.

Notes:
    The hot path stores occupancy and threat masks by spiral index. Each team
    has its own cursor, because once an index becomes invalid for a team it can
    never become valid later. No cursed "start scanning from 0 every turn" crap.
"""

from __future__ import annotations

import argparse
import colorsys
import struct
import sys
import zlib
from array import array
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import repeat
from math import isqrt
from pathlib import Path
from typing import BinaryIO, Iterable, Iterator, Protocol, Sequence


KNIGHT_DELTAS: tuple[tuple[int, int], ...] = (
    (1, 2),
    (2, 1),
    (2, -1),
    (1, -2),
    (-1, -2),
    (-2, -1),
    (-2, 1),
    (-1, 2),
)

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
DEFAULT_TARGET_IMAGE_PX = 1080
ANSI_RESET = "\033[0m"


class UIntStore(Protocol):
    """Storage protocol for unsigned integer values keyed by spiral index."""

    def get(self, index: int) -> int:
        """Return the value at index, or zero when untouched."""

    def set(self, index: int, value: int) -> None:
        """Set value at index."""

    def or_mask(self, index: int, mask: int) -> None:
        """Bitwise-OR mask into index."""


def index_to_coord(index: int) -> tuple[int, int]:
    """Return the (x, y) grid coordinate for a zero-based spiral index."""
    if index < 0:
        raise ValueError("Spiral index must be non-negative.")

    if index == 0:
        return 0, 0

    ring = (isqrt(index) + 1) // 2
    base = (2 * ring - 1) * (2 * ring - 1)
    offset = index - base
    side = 2 * ring

    if offset < side:
        return ring, -ring + 1 + offset

    if offset < 2 * side:
        return ring - 1 - (offset - side), ring

    if offset < 3 * side:
        return -ring, ring - 1 - (offset - 2 * side)

    return -ring + 1 + (offset - 3 * side), -ring


def coord_to_index(x: int, y: int) -> int:
    """Return the zero-based spiral index for an (x, y) grid coordinate."""
    ring = max(abs(x), abs(y))

    if ring == 0:
        return 0

    base = (2 * ring - 1) * (2 * ring - 1)
    side = 2 * ring

    if x == ring and y >= -ring + 1:
        offset = y + ring - 1
    elif y == ring:
        offset = side + (ring - 1 - x)
    elif x == -ring:
        offset = 2 * side + (ring - 1 - y)
    else:
        offset = 3 * side + (x + ring - 1)

    return base + offset


def _array_type_for_unsigned(max_value: int) -> str:
    """Return a compact unsigned array typecode able to hold max_value."""
    if max_value <= 0xFF:
        return "B"

    if max_value <= 0xFFFF:
        return "H"

    if max_value <= 0xFFFFFFFF:
        return "I"

    return "Q"


class DenseUIntStore:
    """Growable dense unsigned integer storage with zero as the default value."""

    def __init__(self, max_value: int, initial_capacity: int = 1024) -> None:
        self._typecode = _array_type_for_unsigned(max_value)
        self._values = array(self._typecode, repeat(0, max(1, initial_capacity)))

    def get(self, index: int) -> int:
        """Return the value at index, or zero when index has not been allocated."""
        values = self._values
        if index >= len(values):
            return 0

        return values[index]

    def set(self, index: int, value: int) -> None:
        """Set value at index, growing storage when necessary."""
        self.ensure_capacity(index)
        self._values[index] = value

    def or_mask(self, index: int, mask: int) -> None:
        """Bitwise-OR mask into value at index, growing storage when necessary."""
        self.ensure_capacity(index)
        self._values[index] |= mask

    def ensure_capacity(self, index: int) -> None:
        """Grow storage until index is valid."""
        values = self._values
        current = len(values)
        if index < current:
            return

        new_size = current
        while new_size <= index:
            new_size *= 2

        values.extend(array(self._typecode, repeat(0, new_size - current)))


class SparseUIntStore:
    """Sparse integer storage for very wide masks or extremely sparse indexes."""

    def __init__(self) -> None:
        self._values: dict[int, int] = {}

    def get(self, index: int) -> int:
        """Return the value at index, or zero when index has not been stored."""
        return self._values.get(index, 0)

    def set(self, index: int, value: int) -> None:
        """Set value at index."""
        if value:
            self._values[index] = value
        else:
            self._values.pop(index, None)

    def or_mask(self, index: int, mask: int) -> None:
        """Bitwise-OR mask into value at index."""
        self._values[index] = self._values.get(index, 0) | mask


@dataclass(frozen=True, slots=True)
class Team:
    """Display metadata for a team."""

    name: str
    symbol: str
    ansi_color: str
    rgb_color: tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class Placement:
    """A completed knight placement."""

    turn: int
    team_id: int
    index: int
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class RasterPlan:
    """Resolved raster dimensions and board bounds."""

    min_x: int
    max_x: int
    min_y: int
    max_y: int
    board_width: int
    board_height: int
    image_width: int
    image_height: int
    cell_px: int


class KnightSpiralGame:
    """Greedy multi-team knight placement on a spiral-numbered square grid."""

    def __init__(self, teams: Sequence[Team], initial_capacity: int = 1024) -> None:
        if not teams:
            raise ValueError("At least one team is required.")

        self.teams = list(teams)
        self.team_count = len(teams)
        self.all_team_mask = (1 << self.team_count) - 1
        self.cursors = [0 for _ in self.teams]
        self.turn = 0

        self.occupied: UIntStore = DenseUIntStore(
            max_value=self.team_count,
            initial_capacity=initial_capacity,
        )

        self.threat_masks: UIntStore
        if self.team_count <= 64:
            self.threat_masks = DenseUIntStore(
                max_value=self.all_team_mask,
                initial_capacity=initial_capacity,
            )
        else:
            self.threat_masks = SparseUIntStore()

        self.placed_indices = array("Q")

        self.min_x = 0
        self.max_x = 0
        self.min_y = 0
        self.max_y = 0
        self.has_placements = False

    def run(self, turns: int, *, progress_enabled: bool = False) -> None:
        """Play turn placements."""
        with progress_iter(
            range(turns),
            total=turns,
            desc="Simulating",
            unit="turn",
            enabled=progress_enabled,
        ) as turn_iter:
            for _ in turn_iter:
                self.place_next()

    def place_next(self) -> Placement:
        """Place one knight for the next team and return its placement."""
        team_id = self.turn % self.team_count
        index = self._find_lowest_legal_index(team_id)
        x, y = index_to_coord(index)

        self.occupied.set(index, team_id + 1)
        self.placed_indices.append(index)
        self._mark_threats(team_id, x, y)
        self.cursors[team_id] = index + 1
        self._include_in_bounds(x, y)

        placement = Placement(turn=self.turn, team_id=team_id, index=index, x=x, y=y)
        self.turn += 1
        return placement

    def _find_lowest_legal_index(self, team_id: int) -> int:
        """Find the lowest unoccupied index not threatened by opposing teams."""
        index = self.cursors[team_id]
        own_team_mask = 1 << team_id
        opposing_team_mask = self.all_team_mask ^ own_team_mask
        occupied_get = self.occupied.get
        threat_get = self.threat_masks.get

        while occupied_get(index) or (threat_get(index) & opposing_team_mask):
            index += 1

        self.cursors[team_id] = index
        return index

    def _mark_threats(self, team_id: int, x: int, y: int) -> None:
        """Mark all squares attacked by the new knight."""
        team_mask = 1 << team_id
        threat_or = self.threat_masks.or_mask

        for dx, dy in KNIGHT_DELTAS:
            threat_or(coord_to_index(x + dx, y + dy), team_mask)

    def _include_in_bounds(self, x: int, y: int) -> None:
        """Update occupied bounding box."""
        if not self.has_placements:
            self.min_x = self.max_x = x
            self.min_y = self.max_y = y
            self.has_placements = True
            return

        if x < self.min_x:
            self.min_x = x
        elif x > self.max_x:
            self.max_x = x

        if y < self.min_y:
            self.min_y = y
        elif y > self.max_y:
            self.max_y = y

    def occupied_at_coord(self, x: int, y: int) -> int:
        """Return team_id + 1 for the square at x, y, or zero if empty."""
        return self.occupied.get(coord_to_index(x, y))

    def iter_placements(self) -> Iterable[tuple[int, int, int, int]]:
        """Yield placed knights as (index, team_id, x, y)."""
        occupied_get = self.occupied.get

        for index in self.placed_indices:
            occupant = occupied_get(index)
            if not occupant:
                continue

            x, y = index_to_coord(index)
            yield index, occupant - 1, x, y

    def draw_bounds(self, radius: int | None = None) -> tuple[int, int, int, int]:
        """Return min_x, max_x, min_y, max_y for drawing."""
        if radius is not None:
            return -radius, radius, -radius, radius

        if self.has_placements:
            return self.min_x, self.max_x, self.min_y, self.max_y

        return 0, 0, 0, 0

    def render_text(
        self,
        *,
        radius: int | None = None,
        ansi: bool = True,
        empty: str = ".",
        cell_width: int = 1,
        max_cells: int = 120_000,
    ) -> str:
        """Render the board as text."""
        min_x, max_x, min_y, max_y = self.draw_bounds(radius)
        width = max_x - min_x + 1
        height = max_y - min_y + 1
        total_cells = width * height

        if total_cells > max_cells:
            raise ValueError(
                f"Refusing to draw {total_cells:,} cells. Use --radius or raise --max-draw-cells."
            )

        rows: list[str] = []
        occupied_at_coord = self.occupied_at_coord

        for y in range(max_y, min_y - 1, -1):
            row: list[str] = []
            for x in range(min_x, max_x + 1):
                occupant = occupied_at_coord(x, y)
                if not occupant:
                    token = empty
                else:
                    team = self.teams[occupant - 1]
                    token = team.symbol
                    if ansi and team.ansi_color:
                        token = f"{team.ansi_color}{token}{ANSI_RESET}"

                row.append(token.rjust(cell_width))

            rows.append(" ".join(row))

        return "\n".join(rows)

    def raster_plan(
        self,
        *,
        radius: int | None = None,
        target_px: int = DEFAULT_TARGET_IMAGE_PX,
        cell_px: int | None = None,
        max_pixels: int = 25_000_000,
    ) -> RasterPlan:
        """Resolve raster bounds, scale, and output dimensions."""
        min_x, max_x, min_y, max_y = self.draw_bounds(radius)
        board_width = max_x - min_x + 1
        board_height = max_y - min_y + 1
        scale = cell_px if cell_px is not None else image_cell_scale(board_width, board_height, target_px)

        if scale <= 0:
            raise ValueError("cell_px must be positive.")

        image_width = board_width * scale
        image_height = board_height * scale
        total_pixels = image_width * image_height

        if max_pixels > 0 and total_pixels > max_pixels:
            raise ValueError(
                f"Refusing to write {total_pixels:,} pixels. Raise --max-image-pixels or pass 0 to disable the cap."
            )

        return RasterPlan(
            min_x=min_x,
            max_x=max_x,
            min_y=min_y,
            max_y=max_y,
            board_width=board_width,
            board_height=board_height,
            image_width=image_width,
            image_height=image_height,
            cell_px=scale,
        )

    def save_ppm(
        self,
        output_path: Path,
        *,
        radius: int | None = None,
        target_px: int = DEFAULT_TARGET_IMAGE_PX,
        cell_px: int | None = None,
        max_pixels: int = 25_000_000,
        empty_rgb: tuple[int, int, int] = (255, 255, 255),
        grid_rgb: tuple[int, int, int] | None = None,
        progress_enabled: bool = False,
    ) -> tuple[int, int, int]:
        """Stream a binary PPM image of the board.

        Returns:
            A tuple of (image_width, image_height, cell_px).
        """
        plan = self.raster_plan(radius=radius, target_px=target_px, cell_px=cell_px, max_pixels=max_pixels)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("wb") as handle:
            handle.write(f"P6\n{plan.image_width} {plan.image_height}\n255\n".encode("ascii"))
            for row in self._iter_raster_rows(
                plan,
                empty_rgb=empty_rgb,
                grid_rgb=grid_rgb,
                progress_enabled=progress_enabled,
            ):
                handle.write(row)

        return plan.image_width, plan.image_height, plan.cell_px

    def save_png(
        self,
        output_path: Path,
        *,
        radius: int | None = None,
        target_px: int = DEFAULT_TARGET_IMAGE_PX,
        cell_px: int | None = None,
        max_pixels: int = 25_000_000,
        empty_rgb: tuple[int, int, int] = (255, 255, 255),
        grid_rgb: tuple[int, int, int] | None = None,
        compress_level: int = 6,
        progress_enabled: bool = False,
    ) -> tuple[int, int, int]:
        """Stream a truecolor PNG image of the board using only the standard library.

        Returns:
            A tuple of (image_width, image_height, cell_px).
        """
        if not 0 <= compress_level <= 9:
            raise ValueError("PNG compression level must be between 0 and 9.")

        plan = self.raster_plan(radius=radius, target_px=target_px, cell_px=cell_px, max_pixels=max_pixels)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        compressor = zlib.compressobj(compress_level)

        with output_path.open("wb") as handle:
            handle.write(b"\x89PNG\r\n\x1a\n")
            write_png_chunk(
                handle,
                b"IHDR",
                struct.pack(">IIBBBBB", plan.image_width, plan.image_height, 8, 2, 0, 0, 0),
            )

            for row in self._iter_raster_rows(
                plan,
                empty_rgb=empty_rgb,
                grid_rgb=grid_rgb,
                progress_enabled=progress_enabled,
            ):
                compressed = compressor.compress(b"\x00" + row)
                if compressed:
                    write_png_chunk(handle, b"IDAT", compressed)

            compressed = compressor.flush()
            if compressed:
                write_png_chunk(handle, b"IDAT", compressed)

            write_png_chunk(handle, b"IEND", b"")

        return plan.image_width, plan.image_height, plan.cell_px

    def _iter_raster_rows(
        self,
        plan: RasterPlan,
        *,
        empty_rgb: tuple[int, int, int],
        grid_rgb: tuple[int, int, int] | None,
        progress_enabled: bool,
    ) -> Iterator[bytes]:
        """Yield RGB raster rows for the resolved image plan."""
        color_cache: dict[int, bytes] = {}
        empty_bytes = bytes(empty_rgb)
        grid_bytes = bytes(grid_rgb) if grid_rgb is not None else None
        occupied_at_coord = self.occupied_at_coord

        def rgb_bytes_for_occupant(occupant: int) -> bytes:
            if not occupant:
                return empty_bytes

            cached = color_cache.get(occupant)
            if cached is not None:
                return cached

            rgb_bytes = bytes(self.teams[occupant - 1].rgb_color)
            color_cache[occupant] = rgb_bytes
            return rgb_bytes

        with progress_iter(
            range(plan.max_y, plan.min_y - 1, -1),
            total=plan.board_height,
            desc="Rasterizing",
            unit="board-row",
            enabled=progress_enabled,
        ) as y_values:
            for y in y_values:
                cell_colors = [
                    rgb_bytes_for_occupant(occupied_at_coord(x, y))
                    for x in range(plan.min_x, plan.max_x + 1)
                ]

                for inner_y in range(plan.cell_px):
                    row = bytearray()
                    horizontal_grid = grid_bytes is not None and plan.cell_px >= 3 and inner_y == plan.cell_px - 1

                    if horizontal_grid:
                        row.extend(grid_bytes * plan.image_width)
                    elif grid_bytes is not None and plan.cell_px >= 3:
                        fill_width = plan.cell_px - 1
                        for cell_color in cell_colors:
                            row.extend(cell_color * fill_width)
                            row.extend(grid_bytes)
                    else:
                        for cell_color in cell_colors:
                            row.extend(cell_color * plan.cell_px)

                    yield bytes(row)

    def summary(self) -> str:
        """Return a compact text summary of the current game state."""
        if not self.has_placements:
            return "No placements yet."

        width = self.max_x - self.min_x + 1
        height = self.max_y - self.min_y + 1
        max_index = max(self.placed_indices) if self.placed_indices else 0
        return (
            f"turns={self.turn:,}, teams={self.team_count}, "
            f"occupied={len(self.placed_indices):,}, max_index={max_index:,}, "
            f"bounds=x[{self.min_x},{self.max_x}] y[{self.min_y},{self.max_y}] "
            f"({width}x{height})"
        )


@contextmanager
def progress_iter(
    iterable: Iterable[int],
    *,
    total: int,
    desc: str,
    unit: str,
    enabled: bool,
) -> Iterator[Iterable[int]]:
    """Wrap an iterable with tqdm when enabled and available."""
    if not enabled:
        yield iterable
        return

    try:
        from tqdm.auto import tqdm
    except ImportError:
        print("tqdm is not installed; continuing without progress. Install it with: python3 -m pip install tqdm", file=sys.stderr)
        yield iterable
        return

    with tqdm(iterable, total=total, desc=desc, unit=unit, dynamic_ncols=True) as progress:
        yield progress


def write_png_chunk(handle: BinaryIO, chunk_type: bytes, data: bytes) -> None:
    """Write one PNG chunk with CRC."""
    handle.write(struct.pack(">I", len(data)))
    handle.write(chunk_type)
    handle.write(data)
    handle.write(struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF))


def raster_format_for_path(path: Path) -> str:
    """Return the raster format implied by path, defaulting to PNG."""
    suffix = path.suffix.lower()
    if suffix in {".ppm", ".pnm"}:
        return "ppm"

    return "png"


def image_cell_scale(board_width: int, board_height: int, target_px: int) -> int:
    """Return automatic pixels-per-cell scaling for a target image size."""
    if target_px <= 0:
        return 1

    larger_dimension = max(board_width, board_height)
    if larger_dimension <= 0 or larger_dimension >= target_px:
        return 1

    return max(1, target_px // larger_dimension)


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


def parse_teams(
    raw_teams: Sequence[str] | None,
    raw_symbols: Sequence[str] | None,
    raw_colors: Sequence[str],
) -> list[Team]:
    """Build team display metadata from CLI values."""
    if raw_teams is None:
        if raw_colors:
            team_names = [f"team_{index + 1}" for index in range(len(raw_colors))]
        else:
            team_names = ["black", "red"]
    else:
        team_names = list(raw_teams)

    color_values = list(raw_colors) if raw_colors else list(DEFAULT_COLORS)

    if len(color_values) < len(team_names):
        for index in range(len(color_values), len(team_names)):
            color_values.append(rgb_to_hex(generated_rgb(index, len(team_names))))
    elif len(color_values) > len(team_names):
        if raw_teams is not None:
            raise ValueError("When --teams is provided, --color must not provide more colors than teams.")

        team_names = [f"team_{index + 1}" for index in range(len(color_values))]

    if raw_symbols and len(raw_symbols) != len(team_names):
        raise ValueError("--symbols must contain exactly one symbol per team.")

    fallback_symbols = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    teams: list[Team] = []

    for index, name in enumerate(team_names):
        lower_name = name.lower().replace("-", "_")
        symbol = raw_symbols[index] if raw_symbols else fallback_symbols[index % len(fallback_symbols)]
        teams.append(
            Team(
                name=name,
                symbol=symbol,
                ansi_color=ANSI_COLORS.get(lower_name, ""),
                rgb_color=parse_rgb(color_values[index]),
            )
        )

    return teams


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Return #RRGGBB for an RGB tuple."""
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def self_test_spiral(limit: int = 10_000) -> None:
    """Verify spiral coordinate/index conversions over a prefix of indices."""
    seen: set[tuple[int, int]] = set()

    for index in range(limit):
        coord = index_to_coord(index)
        if coord in seen:
            raise AssertionError(f"Duplicate coordinate {coord} at index {index}.")

        seen.add(coord)
        round_trip = coord_to_index(*coord)
        if round_trip != index:
            raise AssertionError(f"Round trip failed: index={index}, coord={coord}, got={round_trip}.")


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Greedy multi-team knight placement on a spiral-numbered infinite square grid."
    )
    parser.add_argument("turns", type=int, help="Number of turns to simulate.")
    parser.add_argument(
        "--teams",
        nargs="+",
        default=None,
        help="Team names in turn order. Default: black red unless --color defines a different team count.",
    )
    parser.add_argument(
        "--color",
        "--colors",
        action="append",
        nargs="+",
        dest="colors",
        default=None,
        help="Team colors in turn order. Repeatable and accepts multiple values. Default: #000000 #CC0000.",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Terminal display symbols in team order. Example: --symbols K R",
    )
    parser.add_argument(
        "--radius",
        type=int,
        default=None,
        help="Draw only a square window around the origin with this radius.",
    )
    parser.add_argument(
        "--no-ansi",
        action="store_true",
        help="Disable ANSI terminal colors.",
    )
    parser.add_argument(
        "--no-draw",
        action="store_true",
        help="Do not print the terminal board.",
    )
    parser.add_argument(
        "--draw-text",
        action="store_true",
        help="Force terminal board output even when writing an image.",
    )
    parser.add_argument(
        "--image",
        "--ppm",
        type=Path,
        default=None,
        help="Write a binary PPM image. Kept for compatibility; --raster is usually nicer now.",
    )
    parser.add_argument(
        "--raster",
        "--png",
        type=Path,
        default=None,
        help="Write a raster image. Defaults to PNG; .ppm/.pnm paths write PPM.",
    )
    parser.add_argument(
        "--target-px",
        type=int,
        default=DEFAULT_TARGET_IMAGE_PX,
        help=f"Target larger image dimension for auto-scaling. Default: {DEFAULT_TARGET_IMAGE_PX}.",
    )
    parser.add_argument(
        "--cell-px",
        type=int,
        default=None,
        help="Pixels per board cell for image output. Overrides automatic scaling.",
    )
    parser.add_argument(
        "--empty-color",
        default="#FFFFFF",
        help="Empty-square color for image output. Default: #FFFFFF.",
    )
    parser.add_argument(
        "--grid-color",
        default=None,
        help="Optional grid-line color for image output. Quote #hex values or use --grid-color=#DDDDDD.",
    )
    parser.add_argument(
        "--png-compress-level",
        type=int,
        default=6,
        help="PNG compression level from 0 to 9. Default: 6.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable tqdm progress bars.",
    )
    parser.add_argument(
        "--max-draw-cells",
        type=int,
        default=120_000,
        help="Maximum cells allowed in terminal drawing. Default: 120000.",
    )
    parser.add_argument(
        "--max-image-pixels",
        type=int,
        default=25_000_000,
        help="Maximum output pixels for image drawing. Use 0 to disable. Default: 25000000.",
    )
    parser.add_argument(
        "--cell-width",
        type=int,
        default=1,
        help="Minimum text width per board cell. Default: 1.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run spiral mapping self-tests before simulation.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI."""
    args = build_parser().parse_args(argv)

    if args.turns < 0:
        raise ValueError("turns must be non-negative.")

    if args.radius is not None and args.radius < 0:
        raise ValueError("--radius must be non-negative.")

    if args.target_px < 0:
        raise ValueError("--target-px must be non-negative.")

    if args.cell_px is not None and args.cell_px <= 0:
        raise ValueError("--cell-px must be positive.")

    if args.max_image_pixels < 0:
        raise ValueError("--max-image-pixels must be non-negative.")

    if not 0 <= args.png_compress_level <= 9:
        raise ValueError("--png-compress-level must be between 0 and 9.")

    if args.self_test:
        self_test_spiral()

    teams = parse_teams(args.teams, args.symbols, flatten_color_args(args.colors))
    game = KnightSpiralGame(teams)
    progress_enabled = not args.no_progress
    game.run(args.turns, progress_enabled=progress_enabled)

    print(game.summary())

    if args.image is not None:
        image_width, image_height, actual_cell_px = game.save_ppm(
            args.image,
            radius=args.radius,
            target_px=args.target_px,
            cell_px=args.cell_px,
            max_pixels=args.max_image_pixels,
            empty_rgb=parse_rgb(args.empty_color),
            grid_rgb=parse_rgb(args.grid_color) if args.grid_color else None,
            progress_enabled=progress_enabled,
        )
        print(f"wrote PPM {args.image} ({image_width}x{image_height}, cell_px={actual_cell_px})")

    if args.raster is not None:
        raster_format = raster_format_for_path(args.raster)
        if raster_format == "ppm":
            image_width, image_height, actual_cell_px = game.save_ppm(
                args.raster,
                radius=args.radius,
                target_px=args.target_px,
                cell_px=args.cell_px,
                max_pixels=args.max_image_pixels,
                empty_rgb=parse_rgb(args.empty_color),
                grid_rgb=parse_rgb(args.grid_color) if args.grid_color else None,
                progress_enabled=progress_enabled,
            )
        else:
            image_width, image_height, actual_cell_px = game.save_png(
                args.raster,
                radius=args.radius,
                target_px=args.target_px,
                cell_px=args.cell_px,
                max_pixels=args.max_image_pixels,
                empty_rgb=parse_rgb(args.empty_color),
                grid_rgb=parse_rgb(args.grid_color) if args.grid_color else None,
                compress_level=args.png_compress_level,
                progress_enabled=progress_enabled,
            )

        print(f"wrote {raster_format.upper()} {args.raster} ({image_width}x{image_height}, cell_px={actual_cell_px})")

    should_draw_text = args.draw_text or (not args.no_draw and args.image is None and args.raster is None)
    if should_draw_text:
        print()
        print(
            game.render_text(
                radius=args.radius,
                ansi=not args.no_ansi,
                cell_width=args.cell_width,
                max_cells=args.max_draw_cells,
            )
        )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130)
