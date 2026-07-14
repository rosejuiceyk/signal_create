"""Reproducible white noise and stateful low-frequency AR(1) drift."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


def gaussian_white_noise(
    sample_count: int,
    rms_V: float,
    rng: np.random.Generator,
) -> npt.NDArray[np.float64]:
    """Generate zero-mean Gaussian noise with the configured RMS in volts."""
    if sample_count <= 0:
        raise ValueError("sample_count must be positive")
    if not math.isfinite(rms_V) or rms_V < 0.0:
        raise ValueError("rms_V must be finite and non-negative")
    if rms_V == 0.0:
        return np.zeros(sample_count, dtype=np.float64)
    return np.asarray(rng.normal(0.0, rms_V, size=sample_count), dtype=np.float64)


@dataclass(slots=True)
class AR1DriftGenerator:
    """Generate stationary low-frequency drift while retaining block-boundary state."""

    rms_V: float
    correlation_s: float
    sample_rate_hz: float
    _initialized: bool = False
    _state_V: float = 0.0

    def __post_init__(self) -> None:
        """Validate the stationary AR(1) parameterization."""
        if not math.isfinite(self.rms_V) or self.rms_V < 0.0:
            raise ValueError("rms_V must be finite and non-negative")
        if not math.isfinite(self.correlation_s) or self.correlation_s <= 0.0:
            raise ValueError("correlation_s must be finite and positive")
        if not math.isfinite(self.sample_rate_hz) or self.sample_rate_hz <= 0.0:
            raise ValueError("sample_rate_hz must be finite and positive")

    def sample(
        self,
        sample_count: int,
        rng: np.random.Generator,
    ) -> npt.NDArray[np.float64]:
        """Generate one contiguous drift block and retain its final state."""
        if sample_count <= 0:
            raise ValueError("sample_count must be positive")
        if self.rms_V == 0.0:
            self._initialized = True
            self._state_V = 0.0
            return np.zeros(sample_count, dtype=np.float64)

        coefficient = math.exp(-1.0 / (self.sample_rate_hz * self.correlation_s))
        innovation_variance_factor = -math.expm1(-2.0 / (self.sample_rate_hz * self.correlation_s))
        innovation_rms_V = self.rms_V * math.sqrt(innovation_variance_factor)
        output = np.empty(sample_count, dtype=np.float64)
        start_index = 0
        if not self._initialized:
            self._state_V = float(rng.normal(0.0, self.rms_V))
            self._initialized = True
            output[0] = self._state_V
            start_index = 1
        innovations = np.asarray(
            rng.normal(0.0, innovation_rms_V, size=sample_count - start_index),
            dtype=np.float64,
        )
        for index, innovation_V in enumerate(innovations, start=start_index):
            self._state_V = coefficient * self._state_V + float(innovation_V)
            output[index] = self._state_V
        return output
