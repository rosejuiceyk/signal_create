"""Rate profiles supported by the Phase 1 truth-event generator."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from he3sim.config import MAX_TRUE_RATE_CPS, MIN_TRUE_RATE_CPS


@dataclass(frozen=True, slots=True)
class ConstantRateProfile:
    """A homogeneous true-arrival rate within the supported counts-per-second range."""

    rate_cps: float

    def __post_init__(self) -> None:
        """Reject non-finite rates outside the documented project envelope."""
        if not np.isfinite(self.rate_cps):
            raise ValueError("rate_cps must be finite")
        if not MIN_TRUE_RATE_CPS <= self.rate_cps <= MAX_TRUE_RATE_CPS:
            raise ValueError("rate_cps must be within [10, 1e7]")

    def rate(self, t_s: float | npt.NDArray[np.float64]) -> float | npt.NDArray[np.float64]:
        """Return the constant rate for scalar or array-valued times."""
        if isinstance(t_s, np.ndarray):
            return np.full(t_s.shape, self.rate_cps, dtype=np.float64)
        return self.rate_cps
