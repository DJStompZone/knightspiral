"""Progress bar helper with an optional tqdm dependency."""

from __future__ import annotations

import sys
from collections.abc import Iterable, Iterator
from contextlib import contextmanager


@contextmanager
def progress_iter(
    iterable: Iterable[int],
    *,
    total: int,
    desc: str,
    unit: str,
    enabled: bool,
) -> Iterator[Iterable[int]]:
    """Wrap an iterable with tqdm when enabled and available."""
    if not enabled:
        yield iterable
        return

    try:
        from tqdm.auto import tqdm
    except ImportError:
        print(
            "tqdm is not installed; continuing without progress. Install it with: python3 -m pip install tqdm",
            file=sys.stderr,
        )
        yield iterable
        return

    with tqdm(iterable, total=total, desc=desc, unit=unit, dynamic_ncols=True) as progress:
        yield progress
