from __future__ import annotations

import json
from pathlib import Path

import pytest

from knightspiral.matrix import (
    compact_count,
    equal_hue_colors,
    main,
    matrix_targets,
    parse_count,
    parse_count_set,
    target_output_path,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0"),
        (100, "100"),
        (1_000, "1k"),
        (10_000, "10k"),
        (100_000, "100k"),
        (1_000_000, "1m"),
        (1_000_000_000, "1b"),
    ],
)
def test_compact_count_labels(value: int, expected: str) -> None:
    assert compact_count(value) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("100", 100),
        ("1k", 1_000),
        ("10k", 10_000),
        ("100k", 100_000),
        ("1m", 1_000_000),
        ("1_000", 1_000),
    ],
)
def test_parse_count_supports_plain_and_compact_values(raw: str, expected: int) -> None:
    assert parse_count(raw) == expected


@pytest.mark.parametrize("raw", ["", "lol", "1x", "k"])
def test_parse_count_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_count(raw)


def test_parse_count_set_supports_ranges_and_suffixes() -> None:
    assert parse_count_set("2-4,1k,10k") == [2, 3, 4, 1_000, 10_000]


def test_parse_count_set_deduplicates_and_sorts_values() -> None:
    assert parse_count_set("10k,2,2,1k") == [2, 1_000, 10_000]


def test_parse_count_set_rejects_descending_ranges() -> None:
    with pytest.raises(ValueError):
        parse_count_set("4-2")


@pytest.mark.parametrize("count", [2, 3, 4, 5, 6, 7, 8, 9])
def test_equal_hue_colors_are_distinct(count: int) -> None:
    colors = equal_hue_colors(count, saturation=0.95, value=0.9, hue_offset=0.0)

    assert len(colors) == count
    assert len(set(colors)) == count
    assert all(color.startswith("#") and len(color) == 7 for color in colors)


def test_target_output_path_uses_compact_labels(tmp_path: Path) -> None:
    assert target_output_path(tmp_path, 4, 1_000_000, "png") == tmp_path / "04-colors" / "knightspiral_04c_1m.png"


def test_matrix_targets_builds_color_major_targets(tmp_path: Path) -> None:
    targets = matrix_targets([100, 1_000], [2, 3], tmp_path, "png")

    assert [target.color_count for target in targets] == [2, 2, 3, 3]
    assert [target.turns for target in targets] == [100, 1_000, 100, 1_000]
    assert targets[0].output_path == tmp_path / "02-colors" / "knightspiral_02c_100.png"
    assert targets[-1].output_path == tmp_path / "03-colors" / "knightspiral_03c_1k.png"


@pytest.mark.visual
@pytest.mark.intensity("quick")
def test_matrix_main_writes_small_pngs_manifests_and_cache(tmp_path: Path) -> None:
    output_dir = tmp_path / "renders"
    cache_root = tmp_path / "cache"

    exit_code = main(
        [
            "--turns",
            "2,3",
            "--color-counts",
            "2",
            "--output-dir",
            str(output_dir),
            "--cache-root",
            str(cache_root),
            "--target-px",
            "16",
            "--no-progress",
        ]
    )

    assert exit_code == 0
    assert (output_dir / "02-colors" / "knightspiral_02c_2.png").exists()
    assert (output_dir / "02-colors" / "knightspiral_02c_3.png").exists()
    assert (output_dir / "palettes.json").exists()
    assert (output_dir / "matrix_results.csv").exists()
    assert (output_dir / "matrix_results.jsonl").exists()
    assert (cache_root / "teams-02" / "turns-000000000002.pkl").exists()
    assert (cache_root / "teams-02" / "turns-000000000003.pkl").exists()


@pytest.mark.visual
@pytest.mark.intensity("quick")
def test_matrix_main_supports_multiple_color_counts(tmp_path: Path) -> None:
    output_dir = tmp_path / "renders"
    cache_root = tmp_path / "cache"

    exit_code = main(
        [
            "--turns",
            "2",
            "--color-counts",
            "2-4",
            "--output-dir",
            str(output_dir),
            "--cache-root",
            str(cache_root),
            "--target-px",
            "16",
            "--no-progress",
        ]
    )

    assert exit_code == 0
    assert (output_dir / "02-colors" / "knightspiral_02c_2.png").exists()
    assert (output_dir / "03-colors" / "knightspiral_03c_2.png").exists()
    assert (output_dir / "04-colors" / "knightspiral_04c_2.png").exists()

    palette_data = json.loads((output_dir / "palettes.json").read_text(encoding="utf-8"))
    assert sorted(palette_data) == ["02", "03", "04"]


@pytest.mark.visual
@pytest.mark.intensity("quick")
def test_matrix_main_resume_skips_existing_outputs(tmp_path: Path) -> None:
    output_dir = tmp_path / "renders"
    cache_root = tmp_path / "cache"

    args = [
        "--turns",
        "2",
        "--color-counts",
        "2",
        "--output-dir",
        str(output_dir),
        "--cache-root",
        str(cache_root),
        "--target-px",
        "16",
        "--no-progress",
    ]

    assert main(args) == 0

    output_path = output_dir / "02-colors" / "knightspiral_02c_2.png"
    before = output_path.stat().st_mtime_ns

    assert main([*args, "--resume"]) == 0

    after = output_path.stat().st_mtime_ns
    assert after == before


@pytest.mark.intensity("smoke")
def test_matrix_main_dry_run_writes_manifests_without_images(tmp_path: Path) -> None:
    output_dir = tmp_path / "renders"
    cache_root = tmp_path / "cache"

    exit_code = main(
        [
            "--turns",
            "2",
            "--color-counts",
            "2",
            "--output-dir",
            str(output_dir),
            "--cache-root",
            str(cache_root),
            "--dry-run",
            "--no-progress",
        ]
    )

    assert exit_code == 0
    assert not (output_dir / "02-colors" / "knightspiral_02c_2.png").exists()
    assert (output_dir / "matrix_results.csv").exists()
    assert (output_dir / "matrix_results.jsonl").exists()


@pytest.mark.visual
@pytest.mark.intensity("quick")
def test_matrix_main_supports_ppm_output(tmp_path: Path) -> None:
    output_dir = tmp_path / "renders"
    cache_root = tmp_path / "cache"

    exit_code = main(
        [
            "--turns",
            "2",
            "--color-counts",
            "2",
            "--output-dir",
            str(output_dir),
            "--cache-root",
            str(cache_root),
            "--image-ext",
            "ppm",
            "--target-px",
            "16",
            "--no-progress",
        ]
    )

    output_path = output_dir / "02-colors" / "knightspiral_02c_2.ppm"

    assert exit_code == 0
    assert output_path.exists()
    assert output_path.read_bytes().startswith(b"P6\n")


@pytest.mark.intensity("smoke")
def test_matrix_main_validates_bad_arguments(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        main(
            [
                "--turns",
                "2",
                "--color-counts",
                "2",
                "--output-dir",
                str(tmp_path),
                "--target-px",
                "-1",
            ]
        )