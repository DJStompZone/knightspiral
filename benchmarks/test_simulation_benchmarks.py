from __future__ import annotations

from pathlib import Path

import pytest

from knightspiral.game import KnightSpiralGame
from knightspiral.matrix import matrix_teams


def build_game(turns: int, color_count: int) -> KnightSpiralGame:
    """Build and run a knight spiral simulation for benchmarking."""
    game = KnightSpiralGame(
        matrix_teams(
            color_count,
            saturation=0.95,
            value=0.90,
            hue_offset=0.0,
        )
    )
    game.run(turns, progress_enabled=False)
    return game


@pytest.mark.parametrize(
    ("turns", "color_count"),
    [
        (1_000, 2),
        (10_000, 2),
        (1_000, 4),
        (10_000, 4),
        (1_000, 9),
        (10_000, 9),
    ],
)
def test_simulation_speed(benchmark, turns: int, color_count: int) -> None:
    """Benchmark core simulation speed."""
    game = benchmark(build_game, turns, color_count)

    assert game.turn == turns
    assert game.team_count == color_count


def render_png(tmp_path: Path, turns: int, color_count: int) -> Path:
    """Build, simulate, and render one PNG."""
    game = build_game(turns, color_count)
    output_path = tmp_path / f"knightspiral_{color_count}c_{turns}.png"

    game.save_png(
        output_path,
        target_px=512,
        max_pixels=0,
        progress_enabled=False,
    )

    return output_path


def test_png_render_speed(benchmark, tmp_path: Path) -> None:
    """Benchmark a small PNG render."""
    output_path = benchmark(render_png, tmp_path, 10_000, 4)

    assert output_path.exists()
    assert output_path.stat().st_size > 0
