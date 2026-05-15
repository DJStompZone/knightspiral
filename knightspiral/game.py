"""Core knight spiral simulation engine and render methods."""

from __future__ import annotations

import struct
import zlib
from array import array
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

from knightspiral.colors import ANSI_RESET
from knightspiral.constants import DEFAULT_TARGET_IMAGE_PX, KNIGHT_DELTAS
from knightspiral.models import Placement, RasterPlan, Team
from knightspiral.progress import progress_iter
from knightspiral.raster import image_cell_scale, write_png_chunk
from knightspiral.spiral import coord_to_index, index_to_coord
from knightspiral.storage import DenseUIntStore, SparseUIntStore, UIntStore


class KnightSpiralGame:
    """Greedy multi-team knight placement on a spiral-numbered square grid."""

    def __init__(self, teams: Sequence[Team], initial_capacity: int = 1024) -> None:
        if not teams:
            raise ValueError("At least one team is required.")

        self.teams = list(teams)
        self.team_count = len(teams)
        self.all_team_mask = (1 << self.team_count) - 1
        self.cursors = [0 for _ in self.teams]
        self.turn = 0

        self.occupied: UIntStore = DenseUIntStore(
            max_value=self.team_count,
            initial_capacity=initial_capacity,
        )

        self.threat_masks: UIntStore
        if self.team_count <= 64:
            self.threat_masks = DenseUIntStore(
                max_value=self.all_team_mask,
                initial_capacity=initial_capacity,
            )
        else:
            self.threat_masks = SparseUIntStore()

        self.placed_indices = array("Q")

        self.min_x = 0
        self.max_x = 0
        self.min_y = 0
        self.max_y = 0
        self.has_placements = False

    def run(self, turns: int, *, progress_enabled: bool = False) -> None:
        """Play turn placements."""
        with progress_iter(
            range(turns),
            total=turns,
            desc="Simulating",
            unit="turn",
            enabled=progress_enabled,
        ) as turn_iter:
            for _ in turn_iter:
                self.place_next()

    def place_next(self) -> Placement:
        """Place one knight for the next team and return its placement."""
        team_id = self.turn % self.team_count
        index = self._find_lowest_legal_index(team_id)
        x, y = index_to_coord(index)

        self.occupied.set(index, team_id + 1)
        self.placed_indices.append(index)
        self._mark_threats(team_id, x, y)
        self.cursors[team_id] = index + 1
        self._include_in_bounds(x, y)

        placement = Placement(turn=self.turn, team_id=team_id, index=index, x=x, y=y)
        self.turn += 1
        return placement

    def _find_lowest_legal_index(self, team_id: int) -> int:
        """Find the lowest unoccupied index not threatened by opposing teams."""
        index = self.cursors[team_id]
        own_team_mask = 1 << team_id
        opposing_team_mask = self.all_team_mask ^ own_team_mask
        occupied_get = self.occupied.get
        threat_get = self.threat_masks.get

        while occupied_get(index) or (threat_get(index) & opposing_team_mask):
            index += 1

        self.cursors[team_id] = index
        return index

    def _mark_threats(self, team_id: int, x: int, y: int) -> None:
        """Mark all squares attacked by the new knight."""
        team_mask = 1 << team_id
        threat_or = self.threat_masks.or_mask

        for dx, dy in KNIGHT_DELTAS:
            threat_or(coord_to_index(x + dx, y + dy), team_mask)

    def _include_in_bounds(self, x: int, y: int) -> None:
        """Update occupied bounding box."""
        if not self.has_placements:
            self.min_x = self.max_x = x
            self.min_y = self.max_y = y
            self.has_placements = True
            return

        if x < self.min_x:
            self.min_x = x
        elif x > self.max_x:
            self.max_x = x

        if y < self.min_y:
            self.min_y = y
        elif y > self.max_y:
            self.max_y = y

    def occupied_at_coord(self, x: int, y: int) -> int:
        """Return team_id + 1 for the square at x, y, or zero if empty."""
        return self.occupied.get(coord_to_index(x, y))

    def iter_placements(self) -> Iterable[tuple[int, int, int, int]]:
        """Yield placed knights as (index, team_id, x, y)."""
        occupied_get = self.occupied.get

        for index in self.placed_indices:
            occupant = occupied_get(index)
            if not occupant:
                continue

            x, y = index_to_coord(index)
            yield index, occupant - 1, x, y

    def draw_bounds(self, radius: int | None = None) -> tuple[int, int, int, int]:
        """Return min_x, max_x, min_y, max_y for drawing."""
        if radius is not None:
            return -radius, radius, -radius, radius

        if self.has_placements:
            return self.min_x, self.max_x, self.min_y, self.max_y

        return 0, 0, 0, 0

    def render_text(
        self,
        *,
        radius: int | None = None,
        ansi: bool = True,
        empty: str = ".",
        cell_width: int = 1,
        max_cells: int = 120_000,
    ) -> str:
        """Render the board as text."""
        min_x, max_x, min_y, max_y = self.draw_bounds(radius)
        width = max_x - min_x + 1
        height = max_y - min_y + 1
        total_cells = width * height

        if total_cells > max_cells:
            raise ValueError(
                f"Refusing to draw {total_cells:,} cells. Use --radius or raise --max-draw-cells."
            )

        rows: list[str] = []
        occupied_at_coord = self.occupied_at_coord

        for y in range(max_y, min_y - 1, -1):
            row: list[str] = []
            for x in range(min_x, max_x + 1):
                occupant = occupied_at_coord(x, y)
                if not occupant:
                    token = empty
                else:
                    team = self.teams[occupant - 1]
                    token = team.symbol
                    if ansi and team.ansi_color:
                        token = f"{team.ansi_color}{token}{ANSI_RESET}"

                row.append(token.rjust(cell_width))

            rows.append(" ".join(row))

        return "\n".join(rows)

    def raster_plan(
        self,
        *,
        radius: int | None = None,
        target_px: int = DEFAULT_TARGET_IMAGE_PX,
        cell_px: int | None = None,
        max_pixels: int = 25_000_000,
    ) -> RasterPlan:
        """Resolve raster bounds, scale, and output dimensions."""
        min_x, max_x, min_y, max_y = self.draw_bounds(radius)
        board_width = max_x - min_x + 1
        board_height = max_y - min_y + 1
        scale = cell_px if cell_px is not None else image_cell_scale(board_width, board_height, target_px)

        if scale <= 0:
            raise ValueError("cell_px must be positive.")

        image_width = board_width * scale
        image_height = board_height * scale
        total_pixels = image_width * image_height

        if max_pixels > 0 and total_pixels > max_pixels:
            raise ValueError(
                f"Refusing to write {total_pixels:,} pixels. Raise --max-image-pixels or pass 0 to disable the cap."
            )

        return RasterPlan(
            min_x=min_x,
            max_x=max_x,
            min_y=min_y,
            max_y=max_y,
            board_width=board_width,
            board_height=board_height,
            image_width=image_width,
            image_height=image_height,
            cell_px=scale,
        )

    def save_ppm(
        self,
        output_path: Path,
        *,
        radius: int | None = None,
        target_px: int = DEFAULT_TARGET_IMAGE_PX,
        cell_px: int | None = None,
        max_pixels: int = 25_000_000,
        empty_rgb: tuple[int, int, int] = (255, 255, 255),
        grid_rgb: tuple[int, int, int] | None = None,
        progress_enabled: bool = False,
    ) -> tuple[int, int, int]:
        """Stream a binary PPM image of the board.

        Returns:
            A tuple of (image_width, image_height, cell_px).
        """
        plan = self.raster_plan(radius=radius, target_px=target_px, cell_px=cell_px, max_pixels=max_pixels)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("wb") as handle:
            handle.write(f"P6\n{plan.image_width} {plan.image_height}\n255\n".encode("ascii"))
            for row in self._iter_raster_rows(
                plan,
                empty_rgb=empty_rgb,
                grid_rgb=grid_rgb,
                progress_enabled=progress_enabled,
            ):
                handle.write(row)

        return plan.image_width, plan.image_height, plan.cell_px

    def save_png(
        self,
        output_path: Path,
        *,
        radius: int | None = None,
        target_px: int = DEFAULT_TARGET_IMAGE_PX,
        cell_px: int | None = None,
        max_pixels: int = 25_000_000,
        empty_rgb: tuple[int, int, int] = (255, 255, 255),
        grid_rgb: tuple[int, int, int] | None = None,
        compress_level: int = 6,
        progress_enabled: bool = False,
    ) -> tuple[int, int, int]:
        """Stream a truecolor PNG image of the board using only the standard library.

        Returns:
            A tuple of (image_width, image_height, cell_px).
        """
        if not 0 <= compress_level <= 9:
            raise ValueError("PNG compression level must be between 0 and 9.")

        plan = self.raster_plan(radius=radius, target_px=target_px, cell_px=cell_px, max_pixels=max_pixels)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        compressor = zlib.compressobj(compress_level)

        with output_path.open("wb") as handle:
            handle.write(b"\x89PNG\r\n\x1a\n")
            write_png_chunk(
                handle,
                b"IHDR",
                struct.pack(">IIBBBBB", plan.image_width, plan.image_height, 8, 2, 0, 0, 0),
            )

            for row in self._iter_raster_rows(
                plan,
                empty_rgb=empty_rgb,
                grid_rgb=grid_rgb,
                progress_enabled=progress_enabled,
            ):
                compressed = compressor.compress(b"\x00" + row)
                if compressed:
                    write_png_chunk(handle, b"IDAT", compressed)

            compressed = compressor.flush()
            if compressed:
                write_png_chunk(handle, b"IDAT", compressed)

            write_png_chunk(handle, b"IEND", b"")

        return plan.image_width, plan.image_height, plan.cell_px

    def _iter_raster_rows(
        self,
        plan: RasterPlan,
        *,
        empty_rgb: tuple[int, int, int],
        grid_rgb: tuple[int, int, int] | None,
        progress_enabled: bool,
    ) -> Iterator[bytes]:
        """Yield RGB raster rows for the resolved image plan."""
        color_cache: dict[int, bytes] = {}
        empty_bytes = bytes(empty_rgb)
        grid_bytes = bytes(grid_rgb) if grid_rgb is not None else None
        occupied_at_coord = self.occupied_at_coord

        def rgb_bytes_for_occupant(occupant: int) -> bytes:
            if not occupant:
                return empty_bytes

            cached = color_cache.get(occupant)
            if cached is not None:
                return cached

            rgb_bytes = bytes(self.teams[occupant - 1].rgb_color)
            color_cache[occupant] = rgb_bytes
            return rgb_bytes

        with progress_iter(
            range(plan.max_y, plan.min_y - 1, -1),
            total=plan.board_height,
            desc="Rasterizing",
            unit="board-row",
            enabled=progress_enabled,
        ) as y_values:
            for y in y_values:
                cell_colors = [
                    rgb_bytes_for_occupant(occupied_at_coord(x, y))
                    for x in range(plan.min_x, plan.max_x + 1)
                ]

                for inner_y in range(plan.cell_px):
                    row = bytearray()
                    horizontal_grid = grid_bytes is not None and plan.cell_px >= 3 and inner_y == plan.cell_px - 1

                    if horizontal_grid:
                        row.extend(grid_bytes * plan.image_width)
                    elif grid_bytes is not None and plan.cell_px >= 3:
                        fill_width = plan.cell_px - 1
                        for cell_color in cell_colors:
                            row.extend(cell_color * fill_width)
                            row.extend(grid_bytes)
                    else:
                        for cell_color in cell_colors:
                            row.extend(cell_color * plan.cell_px)

                    yield bytes(row)

    def summary(self) -> str:
        """Return a compact text summary of the current game state."""
        if not self.has_placements:
            return "No placements yet."

        width = self.max_x - self.min_x + 1
        height = self.max_y - self.min_y + 1
        max_index = max(self.placed_indices) if self.placed_indices else 0
        return (
            f"turns={self.turn:,}, teams={self.team_count}, "
            f"occupied={len(self.placed_indices):,}, max_index={max_index:,}, "
            f"bounds=x[{self.min_x},{self.max_x}] y[{self.min_y},{self.max_y}] "
            f"({width}x{height})"
        )
