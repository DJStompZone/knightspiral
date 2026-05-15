"""Boot-scoped cache helpers for knight spiral simulation snapshots."""

from __future__ import annotations

import os
import pickle
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Final

from knightspiral.game import KnightSpiralGame
from knightspiral.models import Team

CACHE_VERSION: Final[int] = 1
CACHE_DIR_NAME: Final[str] = "knightspiral"
SNAPSHOT_PATTERN: Final[re.Pattern[str]] = re.compile(r"turns-(?P<turns>\d+)\.pkl$")


def current_boot_token() -> str:
    """Return a best-effort token that changes after the current OS boot."""
    linux_boot_id = Path("/proc/sys/kernel/random/boot_id")
    if linux_boot_id.exists():
        try:
            return linux_boot_id.read_text(encoding="utf-8").strip()
        except OSError:
            pass

    boot_epoch_seconds = time.time() - time.monotonic()
    rounded_boot_epoch = round(boot_epoch_seconds / 60) * 60
    return f"{sys.platform}-{rounded_boot_epoch}"


def default_cache_root() -> Path:
    """Return the default boot-scoped cache directory."""
    return Path(tempfile.gettempdir()) / CACHE_DIR_NAME / "cache" / current_boot_token() / f"v{CACHE_VERSION}"


def snapshot_dir(team_count: int, cache_root: Path | None = None) -> Path:
    """Return the snapshot directory for a team count."""
    root = cache_root if cache_root is not None else default_cache_root()
    return root / f"teams-{team_count:02d}"


def snapshot_path(team_count: int, turns: int, cache_root: Path | None = None) -> Path:
    """Return the snapshot file path for a team count and turn count."""
    return snapshot_dir(team_count, cache_root) / f"turns-{turns:012d}.pkl"


def save_snapshot(game: KnightSpiralGame, cache_root: Path | None = None) -> Path:
    """Persist a game snapshot and return the written path."""
    path = snapshot_path(game.team_count, game.turn, cache_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f".tmp-{os.getpid()}")

    with temp_path.open("wb") as handle:
        pickle.dump(game, handle, protocol=pickle.HIGHEST_PROTOCOL)

    temp_path.replace(path)
    return path


def load_snapshot(path: Path, teams: list[Team] | None = None) -> KnightSpiralGame:
    """Load a persisted game snapshot, optionally replacing display teams."""
    with path.open("rb") as handle:
        game = pickle.load(handle)

    if not isinstance(game, KnightSpiralGame):
        raise TypeError(f"Snapshot did not contain a KnightSpiralGame: {path}")

    if teams is not None:
        if len(teams) != game.team_count:
            raise ValueError(f"Snapshot has {game.team_count} teams, got {len(teams)} replacement teams.")
        game.teams = teams

    return game


def find_best_snapshot(team_count: int, max_turns: int, cache_root: Path | None = None) -> tuple[int, Path] | None:
    """Find the largest cached snapshot not exceeding max_turns."""
    directory = snapshot_dir(team_count, cache_root)
    if not directory.exists():
        return None

    best_turns = -1
    best_path: Path | None = None

    for path in directory.glob("turns-*.pkl"):
        match = SNAPSHOT_PATTERN.match(path.name)
        if match is None:
            continue

        turns = int(match.group("turns"))
        if turns <= max_turns and turns > best_turns:
            best_turns = turns
            best_path = path

    if best_path is None:
        return None

    return best_turns, best_path
