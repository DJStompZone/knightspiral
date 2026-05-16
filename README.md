# Knight Spiral

**Competing knight armies on an infinite spiral chessboard.**

`knightspiral` simulates the red-and-black knight placement process shown in Numberphile's **Red & Black Knights** video, with support for two or more teams, terminal output, and dependency-free PNG/PPM rendering.

The board is an infinite square grid numbered by a counterclockwise square spiral starting at `0` in the center. Teams take turns placing knights. On a team's turn, the knight is placed on the lowest-numbered unoccupied square that is **not attacked by any opposing team's knight**. Friendly attacks do not matter. Knights are polite to enemies, suspiciously chill with their own army, and apparently very good at creating weird emergent territory maps.

## Why this exists

The project is based on the red/black knight spiral problem popularized by Numberphile and connected OEIS entries:

- [Numberphile: Red & Black Knights](https://youtu.be/UiX4CFIiegM)
- [OEIS A392177](https://oeis.org/A392177): squares occupied by black knights in the two-player version
- [OEIS A392178](https://oeis.org/A392178): squares occupied by red knights in the two-player version
- [OEIS A395355](https://oeis.org/A395355): placement order, with black squares positive and red squares negative
- [OEIS A395357](https://oeis.org/A395357): completed spiral read in order, using positive, negative, and zero values

This implementation is intentionally a simulator and renderer, not a proof engine. The goal is to make it easy to generate the patterns, test variations, and avoid turning a fun math object into a 900-line `__main__.py` goblin.

## Features

- Multi-team knight placement on a spiral-numbered infinite board
- Fast cursor-based search per team instead of rescanning from zero every turn
- Dense integer storage for normal team counts
- Sparse threat-mask storage for very large team counts
- Terminal rendering with optional ANSI colors
- PNG output using only the Python standard library
- PPM output for simple/raw image workflows
- Optional `tqdm` progress bars
- Spiral coordinate/index self-test

## Install

From the repository root:

```bash
python3 -m pip install -e .
```

For progress bars and test tools:

```bash
python3 -m pip install -e '.[progress,dev]'
```

## Quick start

Run 100 turns with the default black/red teams:

```bash
knightspiral 100
```

Run without terminal board output:

```bash
knightspiral 100000 --no-draw
```

Write a PNG:

```bash
knightspiral 100000 --raster out/knights.png --no-draw
```

Write a PNG with explicit team colors:

```bash
knightspiral 250000 --teams black red --color '#000000' '#CC0000' --raster out/red-black.png --no-draw
```

Try three teams, because obviously the correct response to unexplained mathematical weirdness is to add more weirdness:

```bash
knightspiral 250000 --teams black red green --color '#000000' '#CC0000' '#00AA00' --raster out/three-team.png --no-draw
```

Force a small text viewport around the origin:

```bash
knightspiral 200 --radius 8 --no-progress --no-ansi
```

Run the spiral mapping self-test before simulation:

```bash
knightspiral 1000 --self-test --no-draw
```

You can also run it as a module:

```bash
python3 -m knightspiral 1000 --no-draw
```

## Rules implemented

For `N` teams, turn `t` belongs to team `t % N`.

The active team places one knight at the smallest spiral index satisfying both conditions:

1. The square is unoccupied.
2. The square is not attacked by any opposing team's knight.

A square attacked by the active team's own knights is legal. A square attacked by allied/same-color knights is not a problem. This is the behavior used for the red/black OEIS problem and generalized here to more teams.

## Spiral convention

The spiral starts at the origin:

```text
0 = (0, 0)
1 = (1, 0)
2 = (1, 1)
3 = (0, 1)
```

It then continues counterclockwise around each square ring.

## CLI reference

```text
usage: knightspiral [-h] [--teams TEAMS [TEAMS ...]] [--color COLORS [COLORS ...]] [--symbols SYMBOLS [SYMBOLS ...]] [--radius RADIUS] [--no-ansi] [--no-draw] [--draw-text] [--image IMAGE] [--raster RASTER] [--target-px TARGET_PX] [--cell-px CELL_PX] [--empty-color EMPTY_COLOR] [--grid-color GRID_COLOR] [--png-compress-level PNG_COMPRESS_LEVEL] [--no-progress] [--max-draw-cells MAX_DRAW_CELLS] [--max-image-pixels MAX_IMAGE_PIXELS] [--cell-width CELL_WIDTH] [--self-test] turns
```

Important options:

| Option | Purpose |
| --- | --- |
| `turns` | Number of placements to simulate. |
| `--teams` | Team names in turn order. Defaults to `black red`. |
| `--color`, `--colors` | Team colors in turn order. Repeatable; accepts named colors, `#RGB`, `#RRGGBB`, or raw `RRGGBB`. |
| `--symbols` | Terminal symbols for teams. Must match team count. |
| `--radius` | Draw only a square viewport around the origin. |
| `--no-draw` | Suppress terminal board rendering. Useful for large runs. |
| `--draw-text` | Force terminal output even when writing an image. |
| `--raster`, `--png` | Write raster output. `.png` writes PNG; `.ppm`/`.pnm` writes PPM. |
| `--image`, `--ppm` | Compatibility alias for writing PPM. |
| `--target-px` | Target larger image dimension for automatic cell scaling. |
| `--cell-px` | Explicit pixels per board cell. Overrides `--target-px`. |
| `--empty-color` | Empty square color for image output. |
| `--grid-color` | Optional grid line color for image output. |
| `--png-compress-level` | PNG compression level, `0` through `9`. |
| `--max-draw-cells` | Safety cap for terminal rendering. |
| `--max-image-pixels` | Safety cap for image rendering. Use `0` to disable. |
| `--self-test` | Validate spiral index/coordinate round trips before running. |

## Python API

```python
from knightspiral import KnightSpiralGame, Team

teams = [
    Team(name="black", symbol="B", ansi_color="", rgb_color=(0, 0, 0)),
    Team(name="red", symbol="R", ansi_color="", rgb_color=(204, 0, 0)),
]

game = KnightSpiralGame(teams)
game.run(1000)
print(game.summary())
game.save_png("out/knights.png")
```

Useful imports exposed at package level:

```python
from knightspiral import coord_to_index, generated_rgb, index_to_coord, parse_rgb, rgb_to_hex, self_test_spiral
```

## Development

Run tests:

```bash
python3 -m pytest
```

Run compile checks:

```bash
python3 -m compileall -q knightspiral tests
```

Build package metadata locally:

```bash
python3 -m pip install -e '.[dev,progress]'
```

## Notes and limitations

- The simulator stores placement state by spiral index, not by dense 2D arrays.
- Image rendering streams rows, so it does not need to keep the whole image in memory.
- PNG writing is intentionally standard-library-only.
- Very large runs can still take time because the search space and attack bookkeeping grow. Math is fun; CPUs still have bills to pay.
- A single-team run is degenerate under this package's generalized team rule: with no opponents, every unoccupied square is legal. Use two or more teams for the red/black-style process.

## License

MIT

## Experiment matrix renders

For larger comparison runs, use the bundled matrix runner. It renders each requested team count once per requested turn count, using equal-spaced HSV colors and a boot-scoped cache in the OS temp directory.

```bash
poetry run knightspiral-matrix --output-dir ../knightspiral-renders --resume
```

By default this runs 2 through 9 colors at 100, 1k, 10k, 100k, and 1m turns, writing files like:

```text
../knightspiral-renders/02-colors/knightspiral_02c_100.png
../knightspiral-renders/04-colors/knightspiral_04c_10k.png
../knightspiral-renders/09-colors/knightspiral_09c_1m.png
```

Useful options:

```bash
poetry run knightspiral-matrix --turns 100,1k,10k,100k,1m --color-counts 2-9 --output-dir ../renders --resume
poetry run knightspiral-matrix --color-counts 3,4,5 --turns 10k,100k --grid-color '#DDDDDD'
poetry run knightspiral-matrix --no-cache --output-dir ../uncached-renders
```

The runner also writes `palettes.json`, `matrix_results.csv`, and `matrix_results.jsonl` into the output directory.

### Snapshot cache

The matrix runner memoizes full simulation snapshots by team count and turn count. The rule state depends on the number of teams, not the display colors, so a cached 4-team simulation can be reused with any 4-color palette.

By default, snapshots live under a boot-scoped directory inside the OS temp folder. That makes them reusable across repeated runs during the same boot without turning your project folder into a pickle landfill. Use `--cache-root` to choose a specific cache location, or `--no-cache` to disable it.

## Quality reports

The project is configured so one pytest command runs the regular tests, benchmark tests, coverage, and Allure result generation:

```bash
poetry run pytest
```

That writes:

```text
reports/allure-results/
reports/allure-report/
reports/allure-history/history.jsonl
reports/coverage-html/index.html
reports/coverage.xml
reports/benchmark.json
reports/artifacts.json
```

The test suite includes severity-tagged, parameterized simulation profiles and visual render checks. The visual tests attach generated PNGs directly to the matching Allure result, so the report shows the actual 2-color, 3-color, and 9-color raster outputs instead of making you play filename archaeology.

Allure Report 3 is configured by `allurerc.mjs`. The report keeps history in `reports/allure-history/history.jsonl`, so repeated local runs build trend charts and status history instead of acting like every test run was born yesterday.

Install the Python-side reporting tools:

```bash
poetry add --group dev pytest pytest-cov pytest-benchmark pyinstrument allure-pytest
```

Install the Allure 3 CLI with Node:

```bash
npm install -g allure
```

Then verify:

```bash
allure --version
```

If the Allure command is not available, pytest still runs and writes the raw artifacts; it just skips the generated HTML report because obviously it cannot invoke a command that does not exist. Computers remain petty.

Useful variants:

```bash
poetry run pytest --no-allure-generate
poetry run pytest --allure-command "npx allure"
poetry run pytest -m visual
poetry run pytest -m "intensity and not visual"
poetry run pytest benchmarks --benchmark-save=baseline
poetry run pytest benchmarks --benchmark-compare=baseline
poetry run pyinstrument -r html -o reports/profile.html -m knightspiral.matrix --turns 100k --color-counts 9 --output-dir ../profile-renders --no-cache
```

For Allure 3 global stdout/stderr attachments, run the whole pytest command through Allure's wrapper:

```bash
allure run -- poetry run pytest
```

That wrapper is optional for normal local development, but it captures process-level logs as global attachments in Allure 3.
