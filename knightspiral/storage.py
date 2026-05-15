"""Unsigned integer storage backends for occupancy and threat masks."""

from __future__ import annotations

from array import array
from itertools import repeat
from typing import Protocol


class UIntStore(Protocol):
    """Storage protocol for unsigned integer values keyed by spiral index."""

    def get(self, index: int) -> int:
        """Return the value at index, or zero when untouched."""

    def set(self, index: int, value: int) -> None:
        """Set value at index."""

    def or_mask(self, index: int, mask: int) -> None:
        """Bitwise-OR mask into index."""


def _array_type_for_unsigned(max_value: int) -> str:
    """Return a compact unsigned array typecode able to hold max_value."""
    if max_value <= 0xFF:
        return "B"

    if max_value <= 0xFFFF:
        return "H"

    if max_value <= 0xFFFFFFFF:
        return "I"

    return "Q"


class DenseUIntStore:
    """Growable dense unsigned integer storage with zero as the default value."""

    def __init__(self, max_value: int, initial_capacity: int = 1024) -> None:
        self._typecode = _array_type_for_unsigned(max_value)
        self._values = array(self._typecode, repeat(0, max(1, initial_capacity)))

    def get(self, index: int) -> int:
        """Return the value at index, or zero when index has not been allocated."""
        values = self._values
        if index >= len(values):
            return 0

        return values[index]

    def set(self, index: int, value: int) -> None:
        """Set value at index, growing storage when necessary."""
        self.ensure_capacity(index)
        self._values[index] = value

    def or_mask(self, index: int, mask: int) -> None:
        """Bitwise-OR mask into value at index, growing storage when necessary."""
        self.ensure_capacity(index)
        self._values[index] |= mask

    def ensure_capacity(self, index: int) -> None:
        """Grow storage until index is valid."""
        values = self._values
        current = len(values)
        if index < current:
            return

        new_size = current
        while new_size <= index:
            new_size *= 2

        values.extend(array(self._typecode, repeat(0, new_size - current)))


class SparseUIntStore:
    """Sparse integer storage for very wide masks or extremely sparse indexes."""

    def __init__(self) -> None:
        self._values: dict[int, int] = {}

    def get(self, index: int) -> int:
        """Return the value at index, or zero when index has not been stored."""
        return self._values.get(index, 0)

    def set(self, index: int, value: int) -> None:
        """Set value at index."""
        if value:
            self._values[index] = value
        else:
            self._values.pop(index, None)

    def or_mask(self, index: int, mask: int) -> None:
        """Bitwise-OR mask into value at index."""
        self._values[index] = self._values.get(index, 0) | mask
