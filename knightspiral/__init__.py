"""Greedy knight placement on an infinite spiral-numbered square grid."""

from __future__ import annotations

from knightspiral.colors import generated_rgb, parse_rgb, rgb_to_hex
from knightspiral.game import KnightSpiralGame
from knightspiral.models import Placement, RasterPlan, Team
from knightspiral.spiral import coord_to_index, index_to_coord, self_test_spiral

__all__ = [
    "KnightSpiralGame",
    "Placement",
    "RasterPlan",
    "Team",
    "coord_to_index",
    "generated_rgb",
    "index_to_coord",
    "parse_rgb",
    "rgb_to_hex",
    "self_test_spiral",
]

__version__ = "0.1.0"
