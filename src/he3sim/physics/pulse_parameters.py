"""Phase 1 fixed pulse parameters with a future conditional-provider boundary."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from he3sim.types import PulseParameterSamples


@dataclass(frozen=True, slots=True)
class FixedPulseParameterProvider:
    """Repeat fixed model time constants without generating a waveform."""

    tau_r_s: float
    tau_d_s: float

    def __post_init__(self) -> None:
        """Require finite time constants satisfying the model ordering."""
        if not np.isfinite(self.tau_r_s) or not np.isfinite(self.tau_d_s):
            raise ValueError("pulse time constants must be finite")
        if self.tau_r_s <= 0.0 or self.tau_d_s <= self.tau_r_s:
            raise ValueError("pulse time constants must satisfy tau_d_s > tau_r_s > 0")

    def sample(
        self,
        amplitude_peak_V: npt.NDArray[np.float64],
        spectrum_component_id: npt.NDArray[np.int16],
        rng: np.random.Generator,
    ) -> PulseParameterSamples:
        """Return aligned constants; ``rng`` is reserved for future stochastic providers."""
        del rng
        amplitudes = np.asarray(amplitude_peak_V, dtype=np.float64)
        components = np.asarray(spectrum_component_id, dtype=np.int16)
        if amplitudes.ndim != 1 or components.ndim != 1:
            raise ValueError("conditioning arrays must be one-dimensional")
        if amplitudes.shape != components.shape:
            raise ValueError("conditioning arrays must have matching shapes")
        if np.any(~np.isfinite(amplitudes)) or np.any(amplitudes <= 0.0):
            raise ValueError("amplitude_peak_V must contain finite positive values")
        return PulseParameterSamples(
            tau_r_s=np.full(amplitudes.shape, self.tau_r_s, dtype=np.float64),
            tau_d_s=np.full(amplitudes.shape, self.tau_d_s, dtype=np.float64),
        )
