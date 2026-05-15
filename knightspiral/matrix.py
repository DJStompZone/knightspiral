"""Experiment matrix runner for knight spiral raster renders."""

from __future__ import annotations

import argparse
import colorsys
import csv
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from knightspiral.cache import default_cache_root, find_best_snapshot, load_snapshot, save_snapshot
from knightspiral.cli import parse_teams
from knightspiral.colors import parse_rgb
from knightspiral.constants import DEFAULT_TARGET_IMAGE_PX
from knightspiral.game import KnightSpiralGame
from knightspiral.models import Team
from knightspiral.raster import raster_format_for_path

DEFAULT_TURNS: Final[tuple[int, ...]] = (100, 1_000, 10_000, 100_000, 1_000_000)
DEFAULT_COLOR_COUNTS: Final[tuple[int, ...]] = tuple(range(2, 10))
DEFAULT_OUTPUT_DIR: Final[Path] = Path("knightspiral-renders")
DEFAULT_IMAGE_EXT: Final[str] = "png"
DEFAULT_EMPTY_COLOR: Final[str] = "#FFFFFF"
DEFAULT_SATURATION: Final[float] = 0.95
DEFAULT_VALUE: Final[float] = 0.90
COUNT_SUFFIXES: Final[tuple[tuple[int, str], ...]] = (
    (1_000_000_000_000, "t"),
    (1_000_000_000, "b"),
    (1_000_000, "m"),
    (1_000, "k"),
)


@dataclass(frozen=True, slots=True)
class MatrixTarget:
    """One output target in the experiment matrix."""

    turns: int
    color_count: int
    output_path: Path


@dataclass(frozen=True, slots=True)
class MatrixResult:
    """Recorded result for one matrix render."""

    turns: int
    turn_label: str
    color_count: int
    output_path: str
    raster_format: str
    image_width: int
    image_height: int
    cell_px: int
    elapsed_seconds: float
    rendered: bool
    snapshot_loaded: bool
    snapshot_saved: bool


def compact_count(value: int) -> str:
    """Format a positive integer as a compact filename label."""
    if value < 0:
        raise ValueError("Count labels require non-negative integers.")

    for divisor, suffix in COUNT_SUFFIXES:
        if value >= divisor and value % divisor == 0:
            return f"{value // divisor}{suffix}"

    return str(value)


def parse_count(raw: str) -> int:
    """Parse plain or compact counts such as 100, 1k, 100k, and 1m."""
    cleaned = raw.strip().lower().replace("_", "")
    if not cleaned:
        raise ValueError("Empty count value.")

    multiplier = 1
    suffix = cleaned[-1]
    if suffix == "k":
        multiplier = 1_000
        cleaned = cleaned[:-1]
    elif suffix == "m":
        multiplier = 1_000_000
        cleaned = cleaned[:-1]
    elif suffix == "b":
        multiplier = 1_000_000_000
        cleaned = cleaned[:-1]
    elif suffix == "t":
        multiplier = 1_000_000_000_000
        cleaned = cleaned[:-1]

    if not cleaned.isdigit():
        raise ValueError(f"Invalid count value: {raw!r}")

    return int(cleaned) * multiplier


def parse_count_set(raw: str) -> list[int]:
    """Parse comma-separated counts and numeric ranges."""
    values: set[int] = set()

    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue

        if "-" in token:
            start_raw, end_raw = token.split("-", 1)
            start = parse_count(start_raw)
            end = parse_count(end_raw)
            if start > end:
                raise ValueError(f"Invalid descending range: {token!r}")
            values.update(range(start, end + 1))
        else:
            values.add(parse_count(token))

    if not values:
        raise ValueError("Expected at least one count.")

    return sorted(values)


def hex_from_hsv(hue: float, saturation: float, value: float) -> str:
    """Convert HSV floats to #RRGGBB."""
    red, green, blue = colorsys.hsv_to_rgb(hue, saturation, value)
    return f"#{round(red * 255):02X}{round(green * 255):02X}{round(blue * 255):02X}"


def equal_hue_colors(count: int, *, saturation: float, value: float, hue_offset: float) -> list[str]:
    """Generate equal-spaced HSV colors."""
    if count < 1:
        raise ValueError("Color count must be at least 1.")

    return [hex_from_hsv((hue_offset + index / count) % 1.0, saturation, value) for index in range(count)]


def matrix_team_names(count: int) -> list[str]:
    """Return deterministic team names for matrix experiments."""
    return [f"team-{index + 1:02d}" for index in range(count)]


def matrix_teams(count: int, *, saturation: float, value: float, hue_offset: float) -> list[Team]:
    """Create display teams for a matrix color count."""
    return parse_teams(
        matrix_team_names(count),
        None,
        equal_hue_colors(count, saturation=saturation, value=value, hue_offset=hue_offset),
    )


def target_output_path(output_dir: Path, color_count: int, turns: int, image_ext: str) -> Path:
    """Return the output path for a matrix render."""
    suffix = image_ext.lstrip(".").lower()
    return output_dir / f"{color_count:02d}-colors" / f"knightspiral_{color_count:02d}c_{compact_count(turns)}.{suffix}"


def matrix_targets(turns: list[int], color_counts: list[int], output_dir: Path, image_ext: str) -> list[MatrixTarget]:
    """Build all matrix render targets."""
    return [
        MatrixTarget(
            turns=turn,
            color_count=color_count,
            output_path=target_output_path(output_dir, color_count, turn, image_ext),
        )
        for color_count in color_counts
        for turn in turns
    ]


def save_palette_manifest(output_dir: Path, palettes: dict[int, list[Team]]) -> None:
    """Write the palettes used by the matrix run."""
    data = {
        f"{color_count:02d}": [
            {
                "name": team.name,
                "symbol": team.symbol,
                "rgb": team.rgb_color,
                "hex": f"#{team.rgb_color[0]:02X}{team.rgb_color[1]:02X}{team.rgb_color[2]:02X}",
            }
            for team in teams
        ]
        for color_count, teams in palettes.items()
    }
    (output_dir / "palettes.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def save_results_manifest(output_dir: Path, results: list[MatrixResult]) -> None:
    """Write CSV and JSONL manifests for completed matrix targets."""
    if not results:
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "matrix_results.csv"
    jsonl_path = output_dir / "matrix_results.jsonl"

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))

    with jsonl_path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(asdict(result), sort_keys=True) + "\n")


def run_until(game: KnightSpiralGame, turns: int, *, progress_enabled: bool) -> None:
    """Advance a game to the requested absolute turn count."""
    remaining = turns - game.turn
    if remaining < 0:
        raise ValueError(f"Game is already at turn {game.turn}, cannot rewind to {turns}.")

    if remaining:
        game.run(remaining, progress_enabled=progress_enabled)


def render_target(
    game: KnightSpiralGame,
    target: MatrixTarget,
    *,
    radius: int | None,
    target_px: int,
    cell_px: int | None,
    max_image_pixels: int,
    empty_rgb: tuple[int, int, int],
    grid_rgb: tuple[int, int, int] | None,
    png_compress_level: int,
    progress_enabled: bool,
) -> tuple[str, int, int, int]:
    """Render one target and return raster metadata."""
    target.output_path.parent.mkdir(parents=True, exist_ok=True)
    raster_format = raster_format_for_path(target.output_path)

    if raster_format == "ppm":
        image_width, image_height, cell_px_used = game.save_ppm(
            target.output_path,
            radius=radius,
            target_px=target_px,
            cell_px=cell_px,
            max_pixels=max_image_pixels,
            empty_rgb=empty_rgb,
            grid_rgb=grid_rgb,
            progress_enabled=progress_enabled,
        )
    else:
        image_width, image_height, cell_px_used = game.save_png(
            target.output_path,
            radius=radius,
            target_px=target_px,
            cell_px=cell_px,
            max_pixels=max_image_pixels,
            empty_rgb=empty_rgb,
            grid_rgb=grid_rgb,
            compress_level=png_compress_level,
            progress_enabled=progress_enabled,
        )

    return raster_format, image_width, image_height, cell_px_used


def render_existing_result(target: MatrixTarget) -> MatrixResult:
    """Return a manifest result for an already-existing target."""
    return MatrixResult(
        turns=target.turns,
        turn_label=compact_count(target.turns),
        color_count=target.color_count,
        output_path=str(target.output_path),
        raster_format=raster_format_for_path(target.output_path),
        image_width=0,
        image_height=0,
        cell_px=0,
        elapsed_seconds=0.0,
        rendered=False,
        snapshot_loaded=False,
        snapshot_saved=False,
    )


def run_color_count(args: argparse.Namespace, color_count: int, targets: list[MatrixTarget], teams: list[Team]) -> list[MatrixResult]:
    """Run every target for one color count."""
    results: list[MatrixResult] = []
    cache_root = Path(args.cache_root).resolve() if args.cache_root is not None else default_cache_root()
    pending_targets = [target for target in targets if not (args.resume and target.output_path.exists())]

    for target in targets:
        if args.resume and target.output_path.exists():
            print(f"SKIP existing {target.output_path}")
            results.append(render_existing_result(target))

    if not pending_targets:
        return results

    max_pending_turns = max(target.turns for target in pending_targets)
    snapshot_loaded = False

    if args.no_cache:
        game = KnightSpiralGame(teams)
    else:
        cached = find_best_snapshot(color_count, max_pending_turns, cache_root)
        if cached is None:
            game = KnightSpiralGame(teams)
        else:
            cached_turns, cached_path = cached
            game = load_snapshot(cached_path, teams=teams)
            snapshot_loaded = True
            print(f"CACHE loaded {color_count:02d} colors at {compact_count(cached_turns)} from {cached_path}")

    pending_by_turn = {target.turns: target for target in pending_targets}

    for turns in sorted(pending_by_turn):
        target = pending_by_turn[turns]
        started_at = time.perf_counter()
        run_until(game, turns, progress_enabled=not args.no_progress)

        snapshot_saved = False
        if not args.no_cache:
            save_snapshot(game, cache_root)
            snapshot_saved = True

        if args.dry_run:
            print(f"DRY {color_count:02d} colors @ {compact_count(turns)} -> {target.output_path}")
            raster_format = raster_format_for_path(target.output_path)
            image_width = image_height = cell_px_used = 0
        else:
            raster_format, image_width, image_height, cell_px_used = render_target(
                game,
                target,
                radius=args.radius,
                target_px=args.target_px,
                cell_px=args.cell_px,
                max_image_pixels=args.max_image_pixels,
                empty_rgb=parse_rgb(args.empty_color),
                grid_rgb=parse_rgb(args.grid_color) if args.grid_color else None,
                png_compress_level=args.png_compress_level,
                progress_enabled=not args.no_progress,
            )
            print(
                f"WROTE {color_count:02d} colors @ {compact_count(turns)} -> "
                f"{target.output_path} ({image_width}x{image_height}, cell_px={cell_px_used})"
            )

        results.append(
            MatrixResult(
                turns=turns,
                turn_label=compact_count(turns),
                color_count=color_count,
                output_path=str(target.output_path),
                raster_format=raster_format,
                image_width=image_width,
                image_height=image_height,
                cell_px=cell_px_used,
                elapsed_seconds=round(time.perf_counter() - started_at, 4),
                rendered=not args.dry_run,
                snapshot_loaded=snapshot_loaded,
                snapshot_saved=snapshot_saved,
            )
        )
        snapshot_loaded = False

    return results


def build_parser() -> argparse.ArgumentParser:
    """Build the matrix runner parser."""
    parser = argparse.ArgumentParser(description="Run knight spiral renders across turn and color-count matrices.")
    parser.add_argument(
        "--turns",
        default=",".join(compact_count(value) for value in DEFAULT_TURNS),
        help="Comma-separated turn counts. Supports compact values like 100,1k,10k,100k,1m.",
    )
    parser.add_argument(
        "--color-counts",
        default="2-9",
        help="Comma-separated color counts or ranges. Default: 2-9.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for generated renders. Default: {DEFAULT_OUTPUT_DIR}.",
    )
    parser.add_argument(
        "--image-ext",
        default=DEFAULT_IMAGE_EXT,
        help=f"Output extension. Use png, ppm, or pnm. Default: {DEFAULT_IMAGE_EXT}.",
    )
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=None,
        help="Cache directory. Default is an OS temp directory scoped to the current boot.",
    )
    parser.add_argument("--no-cache", action="store_true", help="Disable snapshot caching.")
    parser.add_argument("--resume", action="store_true", help="Skip output images that already exist.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned work without writing images.")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress bars.")
    parser.add_argument("--radius", type=int, default=None, help="Render only a radius around the origin.")
    parser.add_argument(
        "--target-px",
        type=int,
        default=DEFAULT_TARGET_IMAGE_PX,
        help=f"Target larger image dimension for auto-scaling. Default: {DEFAULT_TARGET_IMAGE_PX}.",
    )
    parser.add_argument("--cell-px", type=int, default=None, help="Pixels per board cell. Overrides auto-scaling.")
    parser.add_argument(
        "--max-image-pixels",
        type=int,
        default=25_000_000,
        help="Maximum output pixels. Use 0 to disable. Default: 25000000.",
    )
    parser.add_argument("--empty-color", default=DEFAULT_EMPTY_COLOR, help="Empty-square color. Default: #FFFFFF.")
    parser.add_argument("--grid-color", default=None, help="Optional grid color. Omit for no grid.")
    parser.add_argument(
        "--png-compress-level",
        type=int,
        default=6,
        help="PNG compression level from 0 to 9. Default: 6.",
    )
    parser.add_argument("--saturation", type=float, default=DEFAULT_SATURATION, help="HSV saturation. Default: 0.95.")
    parser.add_argument("--value", type=float, default=DEFAULT_VALUE, help="HSV value/brightness. Default: 0.90.")
    parser.add_argument("--hue-offset", type=float, default=0.0, help="Hue offset from 0.0 to 1.0. Default: 0.0.")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    """Validate parsed matrix runner arguments."""
    if args.radius is not None and args.radius < 0:
        raise ValueError("--radius must be non-negative.")

    if args.target_px < 0:
        raise ValueError("--target-px must be non-negative.")

    if args.cell_px is not None and args.cell_px <= 0:
        raise ValueError("--cell-px must be positive.")

    if args.max_image_pixels < 0:
        raise ValueError("--max-image-pixels must be non-negative.")

    if not 0 <= args.png_compress_level <= 9:
        raise ValueError("--png-compress-level must be between 0 and 9.")

    if not 0.0 <= args.saturation <= 1.0:
        raise ValueError("--saturation must be between 0.0 and 1.0.")

    if not 0.0 <= args.value <= 1.0:
        raise ValueError("--value must be between 0.0 and 1.0.")


def main(argv: list[str] | None = None) -> int:
    """Run the matrix CLI."""
    args = build_parser().parse_args(argv)
    validate_args(args)

    turns = parse_count_set(args.turns)
    color_counts = parse_count_set(args.color_counts)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    all_targets = matrix_targets(turns, color_counts, output_dir, args.image_ext)
    palettes = {
        color_count: matrix_teams(
            color_count,
            saturation=args.saturation,
            value=args.value,
            hue_offset=args.hue_offset,
        )
        for color_count in color_counts
    }
    save_palette_manifest(output_dir, palettes)

    cache_root = Path(args.cache_root).resolve() if args.cache_root is not None else default_cache_root()
    if args.no_cache:
        print("CACHE disabled")
    else:
        print(f"CACHE {cache_root}")

    results: list[MatrixResult] = []
    total_targets = len(all_targets)
    print(f"MATRIX {len(color_counts)} color counts x {len(turns)} turn counts = {total_targets} renders")

    for color_count in color_counts:
        color_targets = [target for target in all_targets if target.color_count == color_count]
        print(f"\n== {color_count:02d} colors ==")
        results.extend(run_color_count(args, color_count, color_targets, palettes[color_count]))
        save_results_manifest(output_dir, results)

    save_results_manifest(output_dir, sorted(results, key=lambda item: (item.color_count, item.turns)))
    print(f"\nDone. Outputs written to: {output_dir}")
    return 0


def entrypoint() -> None:
    """Run the matrix CLI as a process entry point."""
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130)


if __name__ == "__main__":
    entrypoint()
