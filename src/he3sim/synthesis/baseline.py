"""Constant bounded baseline generation for Phase 2."""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt


def constant_baseline(sample_count: int, offset_V: float) -> npt.NDArray[np.float64]:
    """Return a constant baseline block in volts."""
    if sample_count <= 0:
        raise ValueError("sample_count must be positive")
    if not math.isfinite(offset_V):
        raise ValueError("offset_V must be finite")
    return np.full(sample_count, offset_V, dtype=np.float64)
