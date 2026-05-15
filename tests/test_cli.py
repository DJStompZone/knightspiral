from __future__ import annotations

from knightspiral.cli import main


def test_cli_zero_turn_self_test_no_draw(capsys) -> None:
    exit_code = main(["0", "--self-test", "--no-progress", "--no-ansi", "--no-draw"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "No placements yet.\n"
    assert captured.err == ""
