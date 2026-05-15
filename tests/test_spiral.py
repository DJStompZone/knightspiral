from __future__ import annotations

import pytest

from knightspiral.spiral import coord_to_index, index_to_coord, self_test_spiral


@pytest.mark.parametrize(
    ("index", "coord"),
    [
        (0, (0, 0)),
        (1, (1, 0)),
        (2, (1, 1)),
        (3, (0, 1)),
        (4, (-1, 1)),
        (5, (-1, 0)),
        (6, (-1, -1)),
        (7, (0, -1)),
        (8, (1, -1)),
        (9, (2, -1)),
    ],
)
def test_known_spiral_prefix(index: int, coord: tuple[int, int]) -> None:
    assert index_to_coord(index) == coord
    assert coord_to_index(*coord) == index


def test_spiral_round_trip_prefix() -> None:
    self_test_spiral(10_000)
