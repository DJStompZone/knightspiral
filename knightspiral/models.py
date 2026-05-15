"""Dataclasses used by the knight spiral simulation."""

from __future__ import annotations

from dataclasses import dataclass


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
