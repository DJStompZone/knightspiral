"""Raster output helpers for PPM and PNG rendering."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import BinaryIO


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
