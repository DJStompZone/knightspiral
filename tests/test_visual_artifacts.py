"""Visual regression smoke tests that attach rendered PNGs to Allure."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pytest

from knightspiral.game import KnightSpiralGame
from knightspiral.matrix import compact_count, matrix_teams
from test_support.allure_support import allure, attach_json, attach_png_file, attach_text


@dataclass(frozen=True, slots=True)
class RenderCase:
    """A small render case intended for fast visual inspection in Allure."""

    name: str
    turns: int
    color_count: int
    target_px: int
    grid: bool
    severity: str


RENDER_CASES = (
    RenderCase("smoke-2c-100", 100, 2, 256, False, allure.severity_level.MINOR),
    RenderCase("grid-3c-1k", 1_000, 3, 384, True, allure.severity_level.NORMAL),
    RenderCase("texture-9c-1k", 1_000, 9, 384, False, allure.severity_level.CRITICAL),
)


@pytest.mark.visual
@pytest.mark.parametrize("case", RENDER_CASES, ids=lambda case: case.name)
@allure.title("Rendered PNG artifact: {param_id}")
@allure.epic("KnightSpiral")
@allure.feature("Raster Rendering")
@allure.story("Allure image attachments")
def test_render_png_attaches_visual_artifact(tmp_path: Path, case: RenderCase) -> None:
    """Render compact PNGs and attach them directly to the Allure test result."""
    allure.dynamic.severity(case.severity)
    allure.dynamic.parameter("turns", compact_count(case.turns))
    allure.dynamic.parameter("color_count", case.color_count)
    allure.dynamic.parameter("target_px", case.target_px)
    allure.dynamic.parameter("grid", case.grid)

    output_path = tmp_path / f"knightspiral_{case.color_count:02d}c_{compact_count(case.turns)}.png"
    grid_rgb = (221, 221, 221) if case.grid else None

    with allure.step("Generate simulation"):
        game = KnightSpiralGame(matrix_teams(case.color_count, saturation=0.95, value=0.90, hue_offset=0.0))
        game.run(case.turns, progress_enabled=False)

    with allure.step("Render PNG"):
        image_width, image_height, cell_px = game.save_png(
            output_path,
            target_px=case.target_px,
            max_pixels=0,
            empty_rgb=(255, 255, 255),
            grid_rgb=grid_rgb,
            progress_enabled=False,
        )

    with allure.step("Attach render outputs"):
        attach_png_file(output_path, f"{case.name}.png")
        attach_json(
            "render-case",
            json.dumps(
                {
                    **asdict(case),
                    "image_width": image_width,
                    "image_height": image_height,
                    "cell_px": cell_px,
                    "output_path": str(output_path),
                },
                indent=2,
                default=str,
            ),
        )
        attach_text("simulation-summary", game.summary())

    assert output_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert output_path.stat().st_size > 0
    assert image_width > 0
    assert image_height > 0
    assert cell_px > 0
