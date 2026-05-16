"""Snapshot cache tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from knightspiral.cache import find_best_snapshot, load_snapshot, save_snapshot, snapshot_path
from knightspiral.game import KnightSpiralGame
from knightspiral.matrix import matrix_teams
from test_support.allure_support import allure, attach_text


@pytest.mark.intensity("cache")
@allure.title("Save, discover, and reload a snapshot cache file")
@allure.epic("KnightSpiral")
@allure.feature("Snapshot Cache")
@allure.story("Semi-persistent simulation memoization")
@allure.severity(allure.severity_level.CRITICAL)
def test_snapshot_cache_round_trip(tmp_path: Path) -> None:
    """Persist a snapshot and reload it with replacement display teams."""
    original_teams = matrix_teams(4, saturation=0.95, value=0.90, hue_offset=0.0)
    replacement_teams = matrix_teams(4, saturation=0.80, value=0.80, hue_offset=0.25)
    game = KnightSpiralGame(original_teams)
    game.run(100, progress_enabled=False)

    with allure.step("Save snapshot"):
        written_path = save_snapshot(game, tmp_path)
        attach_text("snapshot-path", str(written_path))

    with allure.step("Find best snapshot"):
        best = find_best_snapshot(4, 250, tmp_path)

    assert best == (100, written_path)
    assert snapshot_path(4, 100, tmp_path) == written_path

    with allure.step("Reload snapshot with replacement team colors"):
        loaded = load_snapshot(written_path, teams=replacement_teams)

    assert loaded.turn == 100
    assert loaded.team_count == 4
    assert loaded.summary() == game.summary()
    assert loaded.teams == replacement_teams


@pytest.mark.intensity("cache")
@allure.title("Snapshot cache rejects replacement teams with the wrong length")
@allure.epic("KnightSpiral")
@allure.feature("Snapshot Cache")
@allure.story("Snapshot validation")
@allure.severity(allure.severity_level.NORMAL)
def test_snapshot_cache_rejects_wrong_replacement_team_count(tmp_path: Path) -> None:
    """Validate that cached games cannot be loaded with mismatched team metadata."""
    game = KnightSpiralGame(matrix_teams(3, saturation=0.95, value=0.90, hue_offset=0.0))
    game.run(10, progress_enabled=False)
    path = save_snapshot(game, tmp_path)

    with pytest.raises(ValueError, match="Snapshot has 3 teams"):
        load_snapshot(path, teams=matrix_teams(2, saturation=0.95, value=0.90, hue_offset=0.0))
