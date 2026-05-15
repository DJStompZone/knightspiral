"""Command-line interface for the knight spiral simulation."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from knightspiral.colors import ANSI_COLORS, DEFAULT_COLORS, flatten_color_args, generated_rgb, parse_rgb, rgb_to_hex
from knightspiral.constants import DEFAULT_TARGET_IMAGE_PX
from knightspiral.game import KnightSpiralGame
from knightspiral.models import Team
from knightspiral.raster import raster_format_for_path
from knightspiral.spiral import self_test_spiral


def parse_teams(
    raw_teams: Sequence[str] | None,
    raw_symbols: Sequence[str] | None,
    raw_colors: Sequence[str],
) -> list[Team]:
    """Build team display metadata from CLI values."""
    if raw_teams is None:
        if raw_colors:
            team_names = [f"team_{index + 1}" for index in range(len(raw_colors))]
        else:
            team_names = ["black", "red"]
    else:
        team_names = list(raw_teams)

    color_values = list(raw_colors) if raw_colors else list(DEFAULT_COLORS)

    if len(color_values) < len(team_names):
        for index in range(len(color_values), len(team_names)):
            color_values.append(rgb_to_hex(generated_rgb(index, len(team_names))))
    elif len(color_values) > len(team_names):
        if raw_teams is not None:
            raise ValueError("When --teams is provided, --color must not provide more colors than teams.")

        team_names = [f"team_{index + 1}" for index in range(len(color_values))]

    if raw_symbols and len(raw_symbols) != len(team_names):
        raise ValueError("--symbols must contain exactly one symbol per team.")

    fallback_symbols = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    teams: list[Team] = []

    for index, name in enumerate(team_names):
        lower_name = name.lower().replace("-", "_")
        symbol = raw_symbols[index] if raw_symbols else fallback_symbols[index % len(fallback_symbols)]
        teams.append(
            Team(
                name=name,
                symbol=symbol,
                ansi_color=ANSI_COLORS.get(lower_name, ""),
                rgb_color=parse_rgb(color_values[index]),
            )
        )

    return teams


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Greedy multi-team knight placement on a spiral-numbered infinite square grid."
    )
    parser.add_argument("turns", type=int, help="Number of turns to simulate.")
    parser.add_argument(
        "--teams",
        nargs="+",
        default=None,
        help="Team names in turn order. Default: black red unless --color defines a different team count.",
    )
    parser.add_argument(
        "--color",
        "--colors",
        action="append",
        nargs="+",
        dest="colors",
        default=None,
        help="Team colors in turn order. Repeatable and accepts multiple values. Default: #000000 #CC0000.",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Terminal display symbols in team order. Example: --symbols K R",
    )
    parser.add_argument(
        "--radius",
        type=int,
        default=None,
        help="Draw only a square window around the origin with this radius.",
    )
    parser.add_argument(
        "--no-ansi",
        action="store_true",
        help="Disable ANSI terminal colors.",
    )
    parser.add_argument(
        "--no-draw",
        action="store_true",
        help="Do not print the terminal board.",
    )
    parser.add_argument(
        "--draw-text",
        action="store_true",
        help="Force terminal board output even when writing an image.",
    )
    parser.add_argument(
        "--image",
        "--ppm",
        type=Path,
        default=None,
        help="Write a binary PPM image. Kept for compatibility; --raster is usually nicer now.",
    )
    parser.add_argument(
        "--raster",
        "--png",
        type=Path,
        default=None,
        help="Write a raster image. Defaults to PNG; .ppm/.pnm paths write PPM.",
    )
    parser.add_argument(
        "--target-px",
        type=int,
        default=DEFAULT_TARGET_IMAGE_PX,
        help=f"Target larger image dimension for auto-scaling. Default: {DEFAULT_TARGET_IMAGE_PX}.",
    )
    parser.add_argument(
        "--cell-px",
        type=int,
        default=None,
        help="Pixels per board cell for image output. Overrides automatic scaling.",
    )
    parser.add_argument(
        "--empty-color",
        default="#FFFFFF",
        help="Empty-square color for image output. Default: #FFFFFF.",
    )
    parser.add_argument(
        "--grid-color",
        default=None,
        help="Optional grid-line color for image output. Quote #hex values or use --grid-color=#DDDDDD.",
    )
    parser.add_argument(
        "--png-compress-level",
        type=int,
        default=6,
        help="PNG compression level from 0 to 9. Default: 6.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable tqdm progress bars.",
    )
    parser.add_argument(
        "--max-draw-cells",
        type=int,
        default=120_000,
        help="Maximum cells allowed in terminal drawing. Default: 120000.",
    )
    parser.add_argument(
        "--max-image-pixels",
        type=int,
        default=25_000_000,
        help="Maximum output pixels for image drawing. Use 0 to disable. Default: 25000000.",
    )
    parser.add_argument(
        "--cell-width",
        type=int,
        default=1,
        help="Minimum text width per board cell. Default: 1.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run spiral mapping self-tests before simulation.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI."""
    args = build_parser().parse_args(argv)

    if args.turns < 0:
        raise ValueError("turns must be non-negative.")

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

    if args.self_test:
        self_test_spiral()

    teams = parse_teams(args.teams, args.symbols, flatten_color_args(args.colors))
    game = KnightSpiralGame(teams)
    progress_enabled = not args.no_progress
    game.run(args.turns, progress_enabled=progress_enabled)

    print(game.summary())

    if args.image is not None:
        image_width, image_height, actual_cell_px = game.save_ppm(
            args.image,
            radius=args.radius,
            target_px=args.target_px,
            cell_px=args.cell_px,
            max_pixels=args.max_image_pixels,
            empty_rgb=parse_rgb(args.empty_color),
            grid_rgb=parse_rgb(args.grid_color) if args.grid_color else None,
            progress_enabled=progress_enabled,
        )
        print(f"wrote PPM {args.image} ({image_width}x{image_height}, cell_px={actual_cell_px})")

    if args.raster is not None:
        raster_format = raster_format_for_path(args.raster)
        if raster_format == "ppm":
            image_width, image_height, actual_cell_px = game.save_ppm(
                args.raster,
                radius=args.radius,
                target_px=args.target_px,
                cell_px=args.cell_px,
                max_pixels=args.max_image_pixels,
                empty_rgb=parse_rgb(args.empty_color),
                grid_rgb=parse_rgb(args.grid_color) if args.grid_color else None,
                progress_enabled=progress_enabled,
            )
        else:
            image_width, image_height, actual_cell_px = game.save_png(
                args.raster,
                radius=args.radius,
                target_px=args.target_px,
                cell_px=args.cell_px,
                max_pixels=args.max_image_pixels,
                empty_rgb=parse_rgb(args.empty_color),
                grid_rgb=parse_rgb(args.grid_color) if args.grid_color else None,
                compress_level=args.png_compress_level,
                progress_enabled=progress_enabled,
            )

        print(f"wrote {raster_format.upper()} {args.raster} ({image_width}x{image_height}, cell_px={actual_cell_px})")

    should_draw_text = args.draw_text or (not args.no_draw and args.image is None and args.raster is None)
    if should_draw_text:
        print()
        print(
            game.render_text(
                radius=args.radius,
                ansi=not args.no_ansi,
                cell_width=args.cell_width,
                max_cells=args.max_draw_cells,
            )
        )

    return 0


def entrypoint() -> None:
    """Run the CLI as a process entry point."""
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130)
