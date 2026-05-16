"""Parameterized simulation behavior tests with Allure metadata."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import pytest

from knightspiral.game import KnightSpiralGame
from knightspiral.matrix import compact_count, matrix_teams
from test_support.allure_support import allure, attach_json, attach_text


@dataclass(frozen=True, slots=True)
class SimulationProfile:
    """A simulation case with an Allure severity/intensity label."""

    name: str
    turns: int
    color_count: int
    severity: str
    intensity: str


SIMULATION_PROFILES = (
    SimulationProfile("smoke-two-colors", 10, 2, allure.severity_level.TRIVIAL, "smoke"),
    SimulationProfile("quick-three-colors", 100, 3, allure.severity_level.MINOR, "quick"),
    SimulationProfile("medium-four-colors", 1_000, 4, allure.severity_level.NORMAL, "medium"),
    SimulationProfile("heavy-nine-colors", 5_000, 9, allure.severity_level.CRITICAL, "heavy"),
)


@pytest.mark.parametrize("profile", SIMULATION_PROFILES, ids=lambda profile: profile.name)
@pytest.mark.intensity("mixed")
@allure.title("Simulation profile: {param_id}")
@allure.epic("KnightSpiral")
@allure.feature("Simulation")
@allure.story("Parameterized placement profiles")
def test_simulation_profile_reaches_expected_turn(profile: SimulationProfile) -> None:
    """Run representative placement cases across team counts and intensities."""
    allure.dynamic.severity(profile.severity)
    allure.dynamic.tag(profile.intensity, f"{profile.color_count}-colors", compact_count(profile.turns))
    allure.dynamic.parameter("turns", compact_count(profile.turns))
    allure.dynamic.parameter("color_count", profile.color_count)
    allure.dynamic.parameter("intensity", profile.intensity)

    with allure.step("Create deterministic matrix teams"):
        teams = matrix_teams(profile.color_count, saturation=0.95, value=0.90, hue_offset=0.0)
        game = KnightSpiralGame(teams)

    with allure.step("Run simulation"):
        game.run(profile.turns, progress_enabled=False)

    with allure.step("Attach profile and summary"):
        attach_json("simulation-profile", json.dumps(asdict(profile), indent=2, default=str))
        attach_text("simulation-summary", game.summary())

    assert game.turn == profile.turns
    assert game.team_count == profile.color_count
    assert len(game.placed_indices) == profile.turns
    assert game.has_placements


@pytest.mark.parametrize(
    ("turns", "color_count"),
    [
        pytest.param(100, 2, id="2-colors-100"),
        pytest.param(1_000, 3, id="3-colors-1k"),
        pytest.param(1_000, 6, id="6-colors-1k"),
        pytest.param(1_000, 9, id="9-colors-1k"),
    ],
)
@pytest.mark.intensity("distribution")
@allure.title("Team distribution sanity: {param_id}")
@allure.epic("KnightSpiral")
@allure.feature("Simulation")
@allure.story("Team distribution")
@allure.severity(allure.severity_level.NORMAL)
def test_all_teams_receive_placements(turns: int, color_count: int) -> None:
    """Verify each team gets at least one placement in representative multi-team runs."""
    teams = matrix_teams(color_count, saturation=0.95, value=0.90, hue_offset=0.0)
    game = KnightSpiralGame(teams)

    with allure.step("Run simulation"):
        game.run(turns, progress_enabled=False)

    team_counts = {team.name: 0 for team in teams}
    for _index, team_id, _x, _y in game.iter_placements():
        team_counts[teams[team_id].name] += 1

    attach_json("team-counts", json.dumps(team_counts, indent=2, sort_keys=True))

    assert sum(team_counts.values()) == turns
    assert all(count > 0 for count in team_counts.values())
