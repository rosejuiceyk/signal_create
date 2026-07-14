"""Linear deposited-energy to target-peak amplitude mapping."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from he3sim.config import AmplitudeCalibrationConfig, ParameterValue
from he3sim.types import AmplitudeSamples

MAX_TRUNCATION_RESAMPLES = 100


def _required_float(parameter: ParameterValue[float], name: str) -> float:
    """Return a required value without inventing provisional calibration."""
    if parameter.value is None:
        raise ValueError(f"{name} requires calibration or an explicit demonstration value")
    return parameter.value


def _required_int(parameter: ParameterValue[int], name: str) -> int:
    """Return a required integer without inventing provisional calibration."""
    if parameter.value is None:
        raise ValueError(f"{name} requires calibration or an explicit demonstration value")
    return parameter.value


@dataclass(frozen=True, slots=True)
class LinearAmplitudeMapper:
    """Map energy to a positive peak magnitude with independent polarity."""

    gain_V_per_keV: float
    offset_V: float
    spread_std_V: float
    polarity: int

    def __post_init__(self) -> None:
        """Validate direct construction independently of configuration parsing."""
        values = np.asarray(
            [self.gain_V_per_keV, self.offset_V, self.spread_std_V], dtype=np.float64
        )
        if np.any(~np.isfinite(values)):
            raise ValueError("amplitude mapping parameters must be finite")
        if self.gain_V_per_keV <= 0.0:
            raise ValueError("gain_V_per_keV must be positive")
        if self.spread_std_V < 0.0:
            raise ValueError("spread_std_V must be non-negative")
        if self.polarity not in {-1, 1}:
            raise ValueError("polarity must be -1 or 1")

    @classmethod
    def from_config(cls, config: AmplitudeCalibrationConfig) -> LinearAmplitudeMapper:
        """Build the mapper without substituting missing provisional calibration."""
        return cls(
            gain_V_per_keV=_required_float(config.gain_V_per_keV, "gain_V_per_keV"),
            offset_V=_required_float(config.offset_V, "offset_V"),
            spread_std_V=_required_float(config.spread_std_V, "spread_std_V"),
            polarity=_required_int(config.polarity, "polarity"),
        )

    def sample(
        self,
        energy_dep_keV: npt.NDArray[np.float64],
        rng: np.random.Generator,
    ) -> AmplitudeSamples:
        """Sample a zero-truncated Gaussian around the linear response."""
        energies = np.asarray(energy_dep_keV, dtype=np.float64)
        if energies.ndim != 1:
            raise ValueError("energy_dep_keV must be one-dimensional")
        if np.any(~np.isfinite(energies)) or np.any(energies < 0.0):
            raise ValueError("energy_dep_keV must contain finite non-negative values")

        mean_V = self.gain_V_per_keV * energies + self.offset_V
        if self.spread_std_V == 0.0:
            if np.any(mean_V <= 0.0):
                raise ValueError("deterministic amplitude mapping must remain positive")
            amplitudes_V = mean_V.copy()
        else:
            amplitudes_V = rng.normal(mean_V, self.spread_std_V)
            for _ in range(MAX_TRUNCATION_RESAMPLES):
                invalid = amplitudes_V <= 0.0
                if not np.any(invalid):
                    break
                amplitudes_V[invalid] = rng.normal(
                    mean_V[invalid], self.spread_std_V, size=int(np.count_nonzero(invalid))
                )
            if np.any(amplitudes_V <= 0.0):
                raise RuntimeError("failed to sample a positive target peak amplitude")

        polarities = np.full(energies.shape, self.polarity, dtype=np.int16)
        return AmplitudeSamples(amplitude_peak_V=amplitudes_V, polarity=polarities)
