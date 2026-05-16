"""Scientific analysis pipeline for knight spiral experiments."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final

from knightspiral.cache import default_cache_root, find_best_snapshot, load_snapshot, save_snapshot
from knightspiral.colors import rgb_to_hex
from knightspiral.game import KnightSpiralGame
from knightspiral.matrix import (
    DEFAULT_SATURATION,
    DEFAULT_VALUE,
    compact_count,
    matrix_teams,
    parse_count_set,
    run_until,
)
from knightspiral.models import Team
from knightspiral.spiral import coord_to_index, index_to_coord

DEFAULT_OUTPUT_DIR: Final[Path] = Path("knightspiral-science")
DEFAULT_TURNS: Final[str] = "100k,1m"
DEFAULT_COLOR_COUNTS: Final[str] = "2-9"
DEFAULT_COMPONENT_LIMIT: Final[int] = 200_000
QUADRANT_ORDER: Final[tuple[str, ...]] = ("NE", "NW", "SW", "SE")
NORTH_EAST_SOUTH_WEST: Final[tuple[tuple[int, int], ...]] = ((1, 0), (0, 1), (-1, 0), (0, -1))
RIGHT_AND_UP: Final[tuple[tuple[int, int], ...]] = ((1, 0), (0, 1))


@dataclass(frozen=True, slots=True)
class TeamSummary:
    """Per-team aggregate statistics."""

    team_id: int
    name: str
    color: str
    placements: int
    share: float
    centroid_x: float
    centroid_y: float
    mean_radius: float
    max_radius: int
    quadrant_counts: dict[str, int]
    largest_component: int | None = None
    component_count: int | None = None


@dataclass(frozen=True, slots=True)
class ScienceResult:
    """Computed statistics for one analyzed game state."""

    turns: int
    turn_label: str
    color_count: int
    elapsed_seconds: float
    bounds_min_x: int
    bounds_max_x: int
    bounds_min_y: int
    bounds_max_y: int
    board_width: int
    board_height: int
    board_cells: int
    occupied_cells: int
    empty_cells: int
    density: float
    empty_ratio: float
    entropy: float
    dominance: float
    balance_l2: float
    boundary_edges: int
    boundary_density: float
    empty_perimeter_edges: int
    empty_perimeter_density: float
    snapshot_loaded: bool
    snapshot_saved: bool
    component_analysis: bool
    pair_boundaries: list[list[int]]
    quadrant_counts: dict[str, list[int]]
    teams: list[TeamSummary] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ScienceTarget:
    """One scientific analysis target."""

    turns: int
    color_count: int
    teams: list[Team]


def safe_divide(numerator: float, denominator: float) -> float:
    """Divide two numbers, returning zero when the denominator is zero."""
    if denominator == 0:
        return 0.0

    return numerator / denominator


def quadrant_for_coord(x: int, y: int) -> str:
    """Return a deterministic quadrant label for a board coordinate."""
    if x >= 0 and y >= 0:
        return "NE"

    if x < 0 <= y:
        return "NW"

    if x < 0 and y < 0:
        return "SW"

    return "SE"


def normalized_entropy(counts: Sequence[int]) -> float:
    """Return Shannon entropy normalized to the 0..1 range."""
    total = sum(counts)
    if total <= 0 or len(counts) <= 1:
        return 0.0

    entropy = 0.0
    for count in counts:
        if not count:
            continue
        probability = count / total
        entropy -= probability * math.log(probability)

    return entropy / math.log(len(counts))


def balance_l2(counts: Sequence[int]) -> float:
    """Return Euclidean distance from a perfectly balanced team share vector."""
    total = sum(counts)
    if total <= 0 or not counts:
        return 0.0

    expected = 1.0 / len(counts)
    return math.sqrt(sum(((count / total) - expected) ** 2 for count in counts))


def compact_float(value: float) -> str:
    """Format a float for readable Markdown tables."""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def flatten_science_result(result: ScienceResult) -> dict[str, object]:
    """Flatten a result to scalar-ish fields suitable for CSV."""
    row = {
        "turns": result.turns,
        "turn_label": result.turn_label,
        "color_count": result.color_count,
        "elapsed_seconds": result.elapsed_seconds,
        "board_width": result.board_width,
        "board_height": result.board_height,
        "board_cells": result.board_cells,
        "occupied_cells": result.occupied_cells,
        "empty_cells": result.empty_cells,
        "density": result.density,
        "empty_ratio": result.empty_ratio,
        "entropy": result.entropy,
        "dominance": result.dominance,
        "balance_l2": result.balance_l2,
        "boundary_edges": result.boundary_edges,
        "boundary_density": result.boundary_density,
        "empty_perimeter_edges": result.empty_perimeter_edges,
        "empty_perimeter_density": result.empty_perimeter_density,
        "snapshot_loaded": result.snapshot_loaded,
        "snapshot_saved": result.snapshot_saved,
        "component_analysis": result.component_analysis,
    }

    for team in result.teams:
        prefix = f"team_{team.team_id + 1:02d}"
        row[f"{prefix}_name"] = team.name
        row[f"{prefix}_color"] = team.color
        row[f"{prefix}_placements"] = team.placements
        row[f"{prefix}_share"] = team.share
        row[f"{prefix}_centroid_x"] = team.centroid_x
        row[f"{prefix}_centroid_y"] = team.centroid_y
        row[f"{prefix}_mean_radius"] = team.mean_radius
        row[f"{prefix}_max_radius"] = team.max_radius
        row[f"{prefix}_largest_component"] = team.largest_component
        row[f"{prefix}_component_count"] = team.component_count

    return row


def result_to_jsonable(result: ScienceResult) -> dict[str, object]:
    """Convert a nested science result to JSON-friendly data."""
    data = asdict(result)
    data["teams"] = [asdict(team) for team in result.teams]
    return data


def load_best_snapshot_for_target(
    game: KnightSpiralGame | None,
    *,
    color_count: int,
    turns: int,
    cache_root: Path,
    teams: list[Team],
) -> tuple[KnightSpiralGame | None, bool]:
    """Load the best useful snapshot for a target without rewinding the active game."""
    cached = find_best_snapshot(color_count, turns, cache_root)
    if cached is None:
        return game, False

    cached_turns, cached_path = cached
    if game is not None and cached_turns <= game.turn:
        return game, False

    loaded_game = load_snapshot(cached_path, teams=teams)
    print(f"CACHE loaded {color_count:02d} colors at {compact_count(cached_turns)} from {cached_path}")
    return loaded_game, True


def component_stats(game: KnightSpiralGame) -> dict[int, tuple[int, int]]:
    """Return component_count and largest_component per team using 4-neighbor adjacency."""
    coords_by_team: list[set[tuple[int, int]]] = [set() for _ in range(game.team_count)]

    for index in game.placed_indices:
        occupant = game.occupied.get(index)
        if not occupant:
            continue
        coords_by_team[occupant - 1].add(index_to_coord(index))

    stats: dict[int, tuple[int, int]] = {}
    for team_id, remaining in enumerate(coords_by_team):
        component_count = 0
        largest_component = 0

        while remaining:
            seed = remaining.pop()
            component_count += 1
            size = 1
            queue: deque[tuple[int, int]] = deque([seed])

            while queue:
                x, y = queue.popleft()
                for dx, dy in NORTH_EAST_SOUTH_WEST:
                    neighbor = (x + dx, y + dy)
                    if neighbor not in remaining:
                        continue
                    remaining.remove(neighbor)
                    queue.append(neighbor)
                    size += 1

            largest_component = max(largest_component, size)

        stats[team_id] = (component_count, largest_component)

    return stats


def analyze_game(game: KnightSpiralGame, *, component_limit: int = DEFAULT_COMPONENT_LIMIT) -> ScienceResult:
    """Compute scientific statistics for a completed game state."""
    started_at = time.perf_counter()
    team_count = game.team_count
    team_totals = [0 for _ in range(team_count)]
    team_sum_x = [0 for _ in range(team_count)]
    team_sum_y = [0 for _ in range(team_count)]
    team_sum_radius = [0 for _ in range(team_count)]
    team_max_radius = [0 for _ in range(team_count)]
    quadrant_counts = {quadrant: [0 for _ in range(team_count)] for quadrant in QUADRANT_ORDER}
    pair_boundaries = [[0 for _ in range(team_count)] for _ in range(team_count)]
    boundary_edges = 0
    empty_perimeter_edges = 0
    occupied_get = game.occupied.get

    for index in game.placed_indices:
        occupant = occupied_get(index)
        if not occupant:
            continue

        team_id = occupant - 1
        x, y = index_to_coord(index)
        radius = max(abs(x), abs(y))
        team_totals[team_id] += 1
        team_sum_x[team_id] += x
        team_sum_y[team_id] += y
        team_sum_radius[team_id] += radius
        if radius > team_max_radius[team_id]:
            team_max_radius[team_id] = radius

        quadrant_counts[quadrant_for_coord(x, y)][team_id] += 1

        for dx, dy in RIGHT_AND_UP:
            neighbor = occupied_get(coord_to_index(x + dx, y + dy))
            if not neighbor:
                empty_perimeter_edges += 1
                continue

            neighbor_team_id = neighbor - 1
            if neighbor_team_id == team_id:
                continue

            boundary_edges += 1
            pair_boundaries[team_id][neighbor_team_id] += 1
            pair_boundaries[neighbor_team_id][team_id] += 1

        for dx, dy in ((-1, 0), (0, -1)):
            if not occupied_get(coord_to_index(x + dx, y + dy)):
                empty_perimeter_edges += 1

    occupied_cells = sum(team_totals)
    min_x, max_x, min_y, max_y = game.draw_bounds()
    board_width = max_x - min_x + 1
    board_height = max_y - min_y + 1
    board_cells = board_width * board_height
    empty_cells = max(0, board_cells - occupied_cells)
    component_analysis = component_limit > 0 and occupied_cells <= component_limit
    components = component_stats(game) if component_analysis else {}

    team_summaries: list[TeamSummary] = []
    for team_id, team in enumerate(game.teams):
        placements = team_totals[team_id]
        component_count, largest_component = components.get(team_id, (None, None))
        team_summaries.append(
            TeamSummary(
                team_id=team_id,
                name=team.name,
                color=rgb_to_hex(team.rgb_color),
                placements=placements,
                share=safe_divide(placements, occupied_cells),
                centroid_x=safe_divide(team_sum_x[team_id], placements),
                centroid_y=safe_divide(team_sum_y[team_id], placements),
                mean_radius=safe_divide(team_sum_radius[team_id], placements),
                max_radius=team_max_radius[team_id],
                quadrant_counts={quadrant: quadrant_counts[quadrant][team_id] for quadrant in QUADRANT_ORDER},
                largest_component=largest_component,
                component_count=component_count,
            )
        )

    return ScienceResult(
        turns=game.turn,
        turn_label=compact_count(game.turn),
        color_count=team_count,
        elapsed_seconds=round(time.perf_counter() - started_at, 4),
        bounds_min_x=min_x,
        bounds_max_x=max_x,
        bounds_min_y=min_y,
        bounds_max_y=max_y,
        board_width=board_width,
        board_height=board_height,
        board_cells=board_cells,
        occupied_cells=occupied_cells,
        empty_cells=empty_cells,
        density=safe_divide(occupied_cells, board_cells),
        empty_ratio=safe_divide(empty_cells, board_cells),
        entropy=normalized_entropy(team_totals),
        dominance=max((safe_divide(count, occupied_cells) for count in team_totals), default=0.0),
        balance_l2=balance_l2(team_totals),
        boundary_edges=boundary_edges,
        boundary_density=safe_divide(boundary_edges, occupied_cells),
        empty_perimeter_edges=empty_perimeter_edges,
        empty_perimeter_density=safe_divide(empty_perimeter_edges, occupied_cells),
        snapshot_loaded=False,
        snapshot_saved=False,
        component_analysis=component_analysis,
        pair_boundaries=pair_boundaries,
        quadrant_counts=quadrant_counts,
        teams=team_summaries,
    )


def with_cache_flags(result: ScienceResult, *, snapshot_loaded: bool, snapshot_saved: bool) -> ScienceResult:
    """Return a result copy with cache flag metadata updated."""
    return ScienceResult(
        turns=result.turns,
        turn_label=result.turn_label,
        color_count=result.color_count,
        elapsed_seconds=result.elapsed_seconds,
        bounds_min_x=result.bounds_min_x,
        bounds_max_x=result.bounds_max_x,
        bounds_min_y=result.bounds_min_y,
        bounds_max_y=result.bounds_max_y,
        board_width=result.board_width,
        board_height=result.board_height,
        board_cells=result.board_cells,
        occupied_cells=result.occupied_cells,
        empty_cells=result.empty_cells,
        density=result.density,
        empty_ratio=result.empty_ratio,
        entropy=result.entropy,
        dominance=result.dominance,
        balance_l2=result.balance_l2,
        boundary_edges=result.boundary_edges,
        boundary_density=result.boundary_density,
        empty_perimeter_edges=result.empty_perimeter_edges,
        empty_perimeter_density=result.empty_perimeter_density,
        snapshot_loaded=snapshot_loaded,
        snapshot_saved=snapshot_saved,
        component_analysis=result.component_analysis,
        pair_boundaries=result.pair_boundaries,
        quadrant_counts=result.quadrant_counts,
        teams=result.teams,
    )


def analyze_targets(
    targets: Sequence[ScienceTarget],
    *,
    cache_root: Path,
    no_cache: bool,
    no_progress: bool,
    component_limit: int,
) -> list[ScienceResult]:
    """Analyze a target sequence, reusing cache and active games safely."""
    results: list[ScienceResult] = []

    for color_count in sorted({target.color_count for target in targets}):
        color_targets = sorted((target for target in targets if target.color_count == color_count), key=lambda item: item.turns)
        game: KnightSpiralGame | None = None
        print(f"\n== SCIENCE {color_count:02d} colors ==")

        for target in color_targets:
            snapshot_loaded = False
            if not no_cache:
                game, snapshot_loaded = load_best_snapshot_for_target(
                    game,
                    color_count=color_count,
                    turns=target.turns,
                    cache_root=cache_root,
                    teams=target.teams,
                )

            if game is None:
                game = KnightSpiralGame(target.teams)

            run_until(game, target.turns, progress_enabled=not no_progress)
            snapshot_saved = False
            if not no_cache:
                save_snapshot(game, cache_root)
                snapshot_saved = True

            print(f"ANALYZE {color_count:02d} colors @ {compact_count(target.turns)}")
            result = analyze_game(game, component_limit=component_limit)
            results.append(with_cache_flags(result, snapshot_loaded=snapshot_loaded, snapshot_saved=snapshot_saved))

    return results


def write_json(path: Path, data: object) -> None:
    """Write JSON data to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_result_manifests(output_dir: Path, results: Sequence[ScienceResult]) -> None:
    """Write machine-readable science result manifests."""
    if not results:
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    scalar_rows = [flatten_science_result(result) for result in results]
    fieldnames: list[str] = []
    for row in scalar_rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with (output_dir / "science_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in scalar_rows:
            writer.writerow(row)

    with (output_dir / "science_results.jsonl").open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result_to_jsonable(result), sort_keys=True) + "\n")

    snapshots_dir = output_dir / "snapshots"
    for result in results:
        write_json(snapshots_dir / f"science_{result.color_count:02d}c_{result.turn_label}.json", result_to_jsonable(result))


def svg_escape(raw: object) -> str:
    """Return XML-escaped text."""
    return str(raw).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def svg_document(width: int, height: int, body: str) -> str:
    """Wrap SVG body content in a complete SVG document."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#111827}.axis{stroke:#374151;stroke-width:1}.grid{stroke:#E5E7EB;stroke-width:1}.label{font-size:12px}.title{font-size:18px;font-weight:700}.legend{font-size:12px}.muted{fill:#6B7280}</style>\n'
        f"{body}\n"
        "</svg>\n"
    )


def write_text(path: Path, content: str) -> None:
    """Write UTF-8 text, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def scaled_x(index: int, count: int, left: int, width: int) -> float:
    """Return x coordinate for a sequential chart index."""
    if count <= 1:
        return left + width / 2

    return left + (index / (count - 1)) * width


def scaled_y(value: float, min_value: float, max_value: float, top: int, height: int) -> float:
    """Return y coordinate for a chart value."""
    if math.isclose(max_value, min_value):
        return top + height / 2

    return top + (1 - ((value - min_value) / (max_value - min_value))) * height


def line_chart(
    path: Path,
    *,
    title: str,
    series: dict[str, list[tuple[str, float]]],
    colors: dict[str, str] | None = None,
    y_min: float | None = None,
    y_max: float | None = None,
    y_label: str = "value",
) -> None:
    """Write a compact SVG line chart."""
    width = 1100
    height = 620
    left = 90
    top = 70
    plot_width = 850
    plot_height = 420
    all_values = [value for points in series.values() for _, value in points]
    if not all_values:
        return

    min_value = min(all_values) if y_min is None else y_min
    max_value = max(all_values) if y_max is None else y_max
    if math.isclose(min_value, max_value):
        max_value = min_value + 1

    labels = next(iter(series.values()))
    body = [f'<rect width="100%" height="100%" fill="#FFFFFF"/>']
    body.append(f'<text class="title" x="{left}" y="34">{svg_escape(title)}</text>')
    body.append(f'<text class="label muted" x="{left}" y="56">{svg_escape(y_label)}</text>')

    for tick in range(6):
        ratio = tick / 5
        y = top + ratio * plot_height
        value = max_value - ratio * (max_value - min_value)
        body.append(f'<line class="grid" x1="{left}" y1="{y:.2f}" x2="{left + plot_width}" y2="{y:.2f}"/>')
        body.append(f'<text class="label muted" x="12" y="{y + 4:.2f}">{compact_float(value)}</text>')

    body.append(f'<line class="axis" x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}"/>')
    body.append(f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}"/>')

    for index, (label, _) in enumerate(labels):
        if index % max(1, len(labels) // 8) != 0 and index != len(labels) - 1:
            continue
        x = scaled_x(index, len(labels), left, plot_width)
        body.append(f'<text class="label muted" x="{x:.2f}" y="{top + plot_height + 28}" text-anchor="middle">{svg_escape(label)}</text>')

    legend_x = left + plot_width + 32
    legend_y = top
    palette = colors or {}
    fallback_colors = ["#2563EB", "#DC2626", "#16A34A", "#9333EA", "#EA580C", "#0891B2", "#4B5563", "#DB2777"]

    for series_index, (name, points) in enumerate(series.items()):
        color = palette.get(name, fallback_colors[series_index % len(fallback_colors)])
        path_points = [
            f"{scaled_x(index, len(points), left, plot_width):.2f},{scaled_y(value, min_value, max_value, top, plot_height):.2f}"
            for index, (_, value) in enumerate(points)
        ]
        body.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{" ".join(path_points)}"/>')
        for index, (_, value) in enumerate(points):
            x = scaled_x(index, len(points), left, plot_width)
            y = scaled_y(value, min_value, max_value, top, plot_height)
            body.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.5" fill="{color}"/>')

        y = legend_y + series_index * 22
        body.append(f'<rect x="{legend_x}" y="{y - 10}" width="12" height="12" fill="{color}"/>')
        body.append(f'<text class="legend" x="{legend_x + 18}" y="{y}">{svg_escape(name)}</text>')

    write_text(path, svg_document(width, height, "\n".join(body)))


def stacked_bar_chart(path: Path, *, title: str, result: ScienceResult) -> None:
    """Write a quadrant-by-team stacked bar chart for one result."""
    width = 1000
    height = 600
    left = 90
    top = 70
    plot_width = 660
    plot_height = 390
    bar_width = 100
    gap = 55
    body = ['<rect width="100%" height="100%" fill="#FFFFFF"/>']
    body.append(f'<text class="title" x="{left}" y="34">{svg_escape(title)}</text>')
    body.append(f'<line class="axis" x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}"/>')
    body.append(f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}"/>')

    for q_index, quadrant in enumerate(QUADRANT_ORDER):
        x = left + q_index * (bar_width + gap) + 20
        counts = result.quadrant_counts[quadrant]
        total = sum(counts)
        y_cursor = top + plot_height
        for team, count in zip(result.teams, counts, strict=False):
            height_px = safe_divide(count, total) * plot_height
            y_cursor -= height_px
            body.append(
                f'<rect x="{x}" y="{y_cursor:.2f}" width="{bar_width}" height="{height_px:.2f}" fill="{team.color}"/>'
            )
        body.append(f'<text class="label" x="{x + bar_width / 2}" y="{top + plot_height + 28}" text-anchor="middle">{quadrant}</text>')
        body.append(f'<text class="label muted" x="{x + bar_width / 2}" y="{top + plot_height + 46}" text-anchor="middle">n={total:,}</text>')

    legend_x = left + plot_width + 60
    legend_y = top
    for index, team in enumerate(result.teams):
        y = legend_y + index * 24
        body.append(f'<rect x="{legend_x}" y="{y - 12}" width="14" height="14" fill="{team.color}"/>')
        body.append(f'<text class="legend" x="{legend_x + 22}" y="{y}">{svg_escape(team.name)} ({compact_float(team.share)})</text>')

    write_text(path, svg_document(width, height, "\n".join(body)))


def heatmap(path: Path, *, title: str, result: ScienceResult) -> None:
    """Write a team adjacency heatmap for one result."""
    cell = 42
    label_width = 150
    top = 80
    left = 180
    n = result.color_count
    width = max(760, left + n * cell + 260)
    height = top + n * cell + 120
    max_value = max((value for row in result.pair_boundaries for value in row), default=0)
    body = ['<rect width="100%" height="100%" fill="#FFFFFF"/>']
    body.append(f'<text class="title" x="32" y="34">{svg_escape(title)}</text>')
    body.append(f'<text class="label muted" x="32" y="56">Cross-team orthogonal boundary edge counts</text>')

    for team_index, team in enumerate(result.teams):
        x = left + team_index * cell + cell / 2
        y = top + team_index * cell + cell / 2
        body.append(f'<text class="label" x="{x:.2f}" y="{top - 14}" text-anchor="middle">{team_index + 1}</text>')
        body.append(f'<text class="label" x="{left - 16}" y="{y + 4:.2f}" text-anchor="end">{svg_escape(team.name)}</text>')

    for row_index, row in enumerate(result.pair_boundaries):
        for col_index, value in enumerate(row):
            intensity = 0 if max_value == 0 else value / max_value
            shade = round(255 - intensity * 190)
            fill = f"rgb({shade},{shade},{255})"
            x = left + col_index * cell
            y = top + row_index * cell
            body.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" fill="{fill}" stroke="#FFFFFF"/>')
            if value:
                body.append(f'<text class="label" x="{x + cell / 2}" y="{y + cell / 2 + 4}" text-anchor="middle">{value}</text>')

    legend_x = left + n * cell + 42
    body.append(f'<text class="label" x="{legend_x}" y="{top}">max={max_value:,}</text>')
    for index, team in enumerate(result.teams):
        y = top + 28 + index * 22
        body.append(f'<rect x="{legend_x}" y="{y - 12}" width="12" height="12" fill="{team.color}"/>')
        body.append(f'<text class="legend" x="{legend_x + 18}" y="{y}">{index + 1}: {svg_escape(team.name)}</text>')

    write_text(path, svg_document(width, height, "\n".join(body)))


def write_charts(output_dir: Path, results: Sequence[ScienceResult]) -> list[Path]:
    """Write SVG charts and return their paths."""
    if not results:
        return []

    charts_dir = output_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    chart_paths: list[Path] = []
    by_color: dict[int, list[ScienceResult]] = {}
    for result in results:
        by_color.setdefault(result.color_count, []).append(result)

    metric_specs = [
        ("density", "Occupied density", 0.0, 1.0),
        ("empty_ratio", "Empty-cell ratio", 0.0, 1.0),
        ("entropy", "Normalized color entropy", 0.0, 1.0),
        ("dominance", "Largest team share", 0.0, 1.0),
        ("balance_l2", "Distance from equal shares", 0.0, None),
        ("boundary_density", "Cross-team boundary density", 0.0, None),
        ("empty_perimeter_density", "Occupied-to-empty perimeter density", 0.0, None),
    ]

    for attr, title, y_min, y_max in metric_specs:
        series = {
            f"{color_count:02d} colors": [(result.turn_label, float(getattr(result, attr))) for result in sorted(items, key=lambda item: item.turns)]
            for color_count, items in sorted(by_color.items())
        }
        path = charts_dir / f"metric_{attr}.svg"
        line_chart(path, title=title, series=series, y_min=y_min, y_max=y_max, y_label=attr)
        chart_paths.append(path)

    for color_count, items in sorted(by_color.items()):
        sorted_items = sorted(items, key=lambda item: item.turns)
        team_colors = {team.name: team.color for team in sorted_items[-1].teams}
        share_series: dict[str, list[tuple[str, float]]] = {}
        for result in sorted_items:
            for team in result.teams:
                share_series.setdefault(team.name, []).append((result.turn_label, team.share))

        path = charts_dir / f"team_shares_{color_count:02d}c.svg"
        line_chart(
            path,
            title=f"Team shares over time: {color_count:02d} colors",
            series=share_series,
            colors=team_colors,
            y_min=0.0,
            y_max=1.0,
            y_label="team share",
        )
        chart_paths.append(path)

        latest = sorted_items[-1]
        quadrant_path = charts_dir / f"quadrants_{color_count:02d}c_{latest.turn_label}.svg"
        stacked_bar_chart(quadrant_path, title=f"Quadrant team composition: {color_count:02d} colors @ {latest.turn_label}", result=latest)
        chart_paths.append(quadrant_path)

        heatmap_path = charts_dir / f"boundaries_{color_count:02d}c_{latest.turn_label}.svg"
        heatmap(heatmap_path, title=f"Boundary adjacency heatmap: {color_count:02d} colors @ {latest.turn_label}", result=latest)
        chart_paths.append(heatmap_path)

    return chart_paths


def write_summary(output_dir: Path, results: Sequence[ScienceResult], chart_paths: Sequence[Path]) -> None:
    """Write a Markdown science report."""
    lines = [
        "# Knight Spiral Scientific Analysis",
        "",
        "This report measures emergent territorial structure in greedy multi-team knight placement on a spiral-numbered infinite chessboard.",
        "",
        "## Metrics",
        "",
        "- **Density**: occupied cells divided by bounding-box cells.",
        "- **Entropy**: normalized Shannon entropy of team shares; 1.0 means perfectly balanced team counts.",
        "- **Dominance**: largest team share in the analyzed state.",
        "- **Boundary density**: cross-team orthogonal boundary edges per occupied cell.",
        "- **Empty perimeter density**: occupied-to-empty orthogonal edges per occupied cell.",
        "- **Components**: largest 4-neighbor connected region per team when component analysis is enabled for that size.",
        "",
        "## Summary table",
        "",
        "| colors | turns | density | entropy | dominance | boundary density | empty perimeter density | components? |",
        "|---:|---:|---:|---:|---:|---:|---:|:---:|",
    ]

    for result in sorted(results, key=lambda item: (item.color_count, item.turns)):
        lines.append(
            "| "
            f"{result.color_count} | {result.turn_label} | {compact_float(result.density)} | {compact_float(result.entropy)} | "
            f"{compact_float(result.dominance)} | {compact_float(result.boundary_density)} | "
            f"{compact_float(result.empty_perimeter_density)} | {'yes' if result.component_analysis else 'no'} |"
        )

    lines.extend(["", "## Latest-state team shares", ""])
    latest_by_color: dict[int, ScienceResult] = {}
    for result in results:
        previous = latest_by_color.get(result.color_count)
        if previous is None or result.turns > previous.turns:
            latest_by_color[result.color_count] = result

    for color_count, result in sorted(latest_by_color.items()):
        lines.append(f"### {color_count:02d} colors @ {result.turn_label}")
        lines.append("")
        lines.append("| team | color | share | centroid | mean radius | max radius | largest component |")
        lines.append("|---|---|---:|---:|---:|---:|---:|")
        for team in result.teams:
            centroid = f"({compact_float(team.centroid_x)}, {compact_float(team.centroid_y)})"
            lines.append(
                f"| {team.name} | `{team.color}` | {compact_float(team.share)} | {centroid} | "
                f"{compact_float(team.mean_radius)} | {team.max_radius} | {team.largest_component if team.largest_component is not None else 'n/a'} |"
            )
        lines.append("")

    lines.extend(["", "## Charts", ""])
    for path in chart_paths:
        relative = path.relative_to(output_dir).as_posix()
        lines.append(f"- [{relative}]({relative})")

    write_text(output_dir / "summary.md", "\n".join(lines) + "\n")


def build_targets(
    turns: Sequence[int],
    color_counts: Sequence[int],
    *,
    saturation: float,
    value: float,
    hue_offset: float,
) -> list[ScienceTarget]:
    """Build science targets from turn and color-count sequences."""
    palettes = {
        color_count: matrix_teams(color_count, saturation=saturation, value=value, hue_offset=hue_offset)
        for color_count in color_counts
    }
    return [
        ScienceTarget(turns=turn, color_count=color_count, teams=palettes[color_count])
        for color_count in color_counts
        for turn in turns
    ]


def build_parser() -> argparse.ArgumentParser:
    """Build the science CLI parser."""
    parser = argparse.ArgumentParser(description="Run scientific analysis over knight spiral experiment states.")
    parser.add_argument("--turns", default=DEFAULT_TURNS, help="Comma-separated turns to analyze. Default: 100k,1m.")
    parser.add_argument("--color-counts", default=DEFAULT_COLOR_COUNTS, help="Comma-separated color counts/ranges. Default: 2-9.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help=f"Output directory. Default: {DEFAULT_OUTPUT_DIR}.")
    parser.add_argument("--cache-root", type=Path, default=None, help="Snapshot cache root. Default: OS temp boot-scoped cache.")
    parser.add_argument("--no-cache", action="store_true", help="Disable snapshot cache load/save.")
    parser.add_argument("--no-progress", action="store_true", help="Disable simulation progress bars.")
    parser.add_argument("--component-limit", type=int, default=DEFAULT_COMPONENT_LIMIT, help="Max occupied cells for connected-component analysis. Use 0 to disable.")
    parser.add_argument("--saturation", type=float, default=DEFAULT_SATURATION, help="HSV saturation for generated palettes.")
    parser.add_argument("--value", type=float, default=DEFAULT_VALUE, help="HSV value/brightness for generated palettes.")
    parser.add_argument("--hue-offset", type=float, default=0.0, help="Hue offset from 0.0 to 1.0.")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    """Validate parsed science CLI args."""
    if args.component_limit < 0:
        raise ValueError("--component-limit must be non-negative.")

    if not 0.0 <= args.saturation <= 1.0:
        raise ValueError("--saturation must be between 0.0 and 1.0.")

    if not 0.0 <= args.value <= 1.0:
        raise ValueError("--value must be between 0.0 and 1.0.")


def main(argv: list[str] | None = None) -> int:
    """Run the science CLI."""
    args = build_parser().parse_args(argv)
    validate_args(args)
    turns = parse_count_set(args.turns)
    color_counts = parse_count_set(args.color_counts)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_root = Path(args.cache_root).resolve() if args.cache_root is not None else default_cache_root()
    targets = build_targets(
        turns,
        color_counts,
        saturation=args.saturation,
        value=args.value,
        hue_offset=args.hue_offset,
    )

    if args.no_cache:
        print("CACHE disabled")
    else:
        print(f"CACHE {cache_root}")

    print(f"SCIENCE {len(color_counts)} color counts x {len(turns)} turn counts = {len(targets)} analyses")
    results = analyze_targets(
        targets,
        cache_root=cache_root,
        no_cache=args.no_cache,
        no_progress=args.no_progress,
        component_limit=args.component_limit,
    )
    results = sorted(results, key=lambda item: (item.color_count, item.turns))
    write_result_manifests(output_dir, results)
    chart_paths = write_charts(output_dir, results)
    write_summary(output_dir, results, chart_paths)
    print(f"\nDone. Science outputs written to: {output_dir}")
    return 0


def entrypoint() -> None:
    """Run the science CLI as a process entry point."""
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130)


if __name__ == "__main__":
    entrypoint()
