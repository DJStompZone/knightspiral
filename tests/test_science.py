from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from knightspiral.game import KnightSpiralGame
from knightspiral.matrix import matrix_teams
from knightspiral.science import analyze_game, main, parse_count_set

try:
    import allure
except ModuleNotFoundError:  # pragma: no cover
    allure = None  # type: ignore[assignment]


def attach_file(path: Path, name: str, attachment_type: Any = None, extension: str | None = None) -> None:
    """Attach a file to Allure when the plugin is available."""
    if allure is None:
        return

    allure.attach.file(str(path), name=name, attachment_type=attachment_type, extension=extension)


def test_analyze_game_reports_core_metrics() -> None:
    teams = matrix_teams(3, saturation=0.95, value=0.9, hue_offset=0.0)
    game = KnightSpiralGame(teams)
    game.run(100, progress_enabled=False)

    result = analyze_game(game, component_limit=1_000)

    assert result.turns == 100
    assert result.color_count == 3
    assert result.occupied_cells == 100
    assert result.board_cells >= result.occupied_cells
    assert 0.0 <= result.density <= 1.0
    assert 0.0 <= result.entropy <= 1.0
    assert 0.0 <= result.dominance <= 1.0
    assert result.boundary_edges >= 0
    assert len(result.teams) == 3
    assert sum(team.placements for team in result.teams) == 100
    assert all(team.largest_component is not None for team in result.teams)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("100k,1m", [100_000, 1_000_000]),
        ("2-4", [2, 3, 4]),
    ],
)
def test_science_uses_matrix_count_parser(raw: str, expected: list[int]) -> None:
    assert parse_count_set(raw) == expected


def test_science_cli_writes_manifests_charts_and_summary(tmp_path: Path) -> None:
    output_dir = tmp_path / "science"
    cache_root = tmp_path / "cache"

    assert main(
        [
            "--turns",
            "10,100",
            "--color-counts",
            "2-3",
            "--output-dir",
            str(output_dir),
            "--cache-root",
            str(cache_root),
            "--component-limit",
            "1000",
            "--no-progress",
        ]
    ) == 0

    summary_path = output_dir / "summary.md"
    csv_path = output_dir / "science_results.csv"
    jsonl_path = output_dir / "science_results.jsonl"
    density_chart = output_dir / "charts" / "metric_density.svg"
    shares_chart = output_dir / "charts" / "team_shares_03c.svg"
    snapshot_path = output_dir / "snapshots" / "science_03c_100.json"

    assert summary_path.exists()
    assert csv_path.exists()
    assert jsonl_path.exists()
    assert density_chart.exists()
    assert shares_chart.exists()
    assert snapshot_path.exists()

    rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 4
    assert rows[-1]["turns"] == 100
    assert rows[-1]["color_count"] == 3
    assert rows[-1]["occupied_cells"] == 100

    attach_file(summary_path, "science-summary", attachment_type="text/markdown", extension="md")
    attach_file(csv_path, "science-results-csv", attachment_type="text/csv", extension="csv")
    attach_file(density_chart, "science-density-chart", attachment_type="image/svg+xml", extension="svg")
    attach_file(shares_chart, "science-team-shares-chart", attachment_type="image/svg+xml", extension="svg")
    attach_file(snapshot_path, "science-snapshot-json", attachment_type="application/json", extension="json")
