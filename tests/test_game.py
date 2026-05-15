from __future__ import annotations

from knightspiral.cli import parse_teams
from knightspiral.game import KnightSpiralGame


def test_twenty_turn_summary_matches_known_output() -> None:
    game = KnightSpiralGame(parse_teams(None, None, []))
    game.run(20, progress_enabled=False)

    assert game.summary() == "turns=20, teams=2, occupied=20, max_index=35, bounds=x[-2,3] y[-2,3] (6x6)"


def test_three_team_color_expansion() -> None:
    teams = parse_teams(["black", "red", "green"], None, ["#000000"])

    assert [team.name for team in teams] == ["black", "red", "green"]
    assert len({team.rgb_color for team in teams}) == 3
