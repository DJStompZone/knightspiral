"""Spiral coordinate/index conversion helpers."""

from __future__ import annotations

from math import isqrt


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
