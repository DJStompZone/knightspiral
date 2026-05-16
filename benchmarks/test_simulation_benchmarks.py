"""Performance benchmarks for the knightspiral simulation and raster renderer."""

from __future__ import annotations

from pathlib import Path

import pytest

from knightspiral.game import KnightSpiralGame
from knightspiral.matrix import matrix_teams


@pytest.mark.benchmark
@pytest.mark.parametrize(
    ("turns", "color_count"),
    [
        (1_000, 2),
        (1_000, 4),
        (1_000, 9),
        (10_000, 2),
        (10_000, 4),
        (10_000, 9),
    ],
)
def test_simulation_speed(benchmark, turns: int, color_count: int) -> None:
    """Benchmark core placement simulation throughput."""
    game = benchmark(run_simulation, turns, color_count)

    assert game.turn == turns
    assert game.team_count == color_count


@pytest.mark.benchmark
def test_png_render_speed(benchmark, tmp_path: Path) -> None:
    """Benchmark simulation plus PNG raster output for a representative render."""
    output_path = benchmark(render_png, tmp_path, 10_000, 4)

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def run_simulation(turns: int, color_count: int) -> KnightSpiralGame:
    """Build and run a knightspiral simulation."""
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


def render_png(tmp_path: Path, turns: int, color_count: int) -> Path:
    """Run a simulation and render the result to PNG."""
    game = run_simulation(turns, color_count)
    output_path = tmp_path / f"knightspiral_{color_count}c_{turns}.png"
    game.save_png(
        output_path,
        target_px=512,
        max_pixels=0,
        progress_enabled=False,
    )
    return output_path
