from __future__ import annotations

from pathlib import Path

from knightspiral.matrix import compact_count, equal_hue_colors, main, parse_count_set, target_output_path


def test_compact_count_labels() -> None:
    assert compact_count(100) == "100"
    assert compact_count(1_000) == "1k"
    assert compact_count(100_000) == "100k"
    assert compact_count(1_000_000) == "1m"


def test_parse_count_set_supports_ranges_and_suffixes() -> None:
    assert parse_count_set("2-4,1k,10k") == [2, 3, 4, 1_000, 10_000]


def test_equal_hue_colors_are_distinct() -> None:
    colors = equal_hue_colors(9, saturation=0.95, value=0.9, hue_offset=0.0)

    assert len(colors) == 9
    assert len(set(colors)) == 9
    assert all(color.startswith("#") and len(color) == 7 for color in colors)


def test_target_output_path_uses_compact_labels(tmp_path: Path) -> None:
    assert target_output_path(tmp_path, 4, 1_000_000, "png") == tmp_path / "04-colors" / "knightspiral_04c_1m.png"


def test_matrix_main_writes_small_png_and_manifests(tmp_path: Path) -> None:
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
    assert (cache_root / "teams-02" / "turns-000000000002.pkl").exists()
    assert (cache_root / "teams-02" / "turns-000000000003.pkl").exists()
