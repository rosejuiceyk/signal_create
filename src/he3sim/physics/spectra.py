"""Configurable parameterized He-3 deposited-energy spectrum."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import numpy as np

from he3sim.config import EnergySpectrumConfig, ParameterValue
from he3sim.types import SpectrumSamples

MAX_TRUNCATION_RESAMPLES = 100


class SpectrumComponent(IntEnum):
    """Stable component identifiers stored in the truth-event table."""

    FULL_ENERGY = 0
    PROTON_WALL = 1
    TRITON_WALL = 2
    DOUBLE_WALL = 3


def _required(parameter: ParameterValue[float], name: str) -> float:
    """Return a required Phase 1 parameter or fail without inventing a value."""
    if parameter.value is None:
        raise ValueError(f"{name} requires calibration or an explicit demonstration value")
    return parameter.value


@dataclass(frozen=True, slots=True)
class ParametricHe3Spectrum:
    """Mixture of a broadened full-energy peak and three bounded Beta continua."""

    full_energy_keV: float
    full_energy_sigma_keV: float
    weights: tuple[float, float, float, float]
    proton_wall: tuple[float, float, float, float]
    triton_wall: tuple[float, float, float, float]
    double_wall: tuple[float, float, float, float] | None

    def __post_init__(self) -> None:
        """Validate direct construction independently of Pydantic configuration."""
        weights = np.asarray(self.weights, dtype=np.float64)
        if weights.shape != (4,) or np.any(~np.isfinite(weights)) or np.any(weights < 0.0):
            raise ValueError("spectrum weights must be four finite non-negative values")
        if not np.isclose(np.sum(weights), 1.0, rtol=0.0, atol=1.0e-9):
            raise ValueError("spectrum weights must sum to one")
        if not np.isfinite(self.full_energy_keV) or self.full_energy_keV <= 0.0:
            raise ValueError("full_energy_keV must be finite and positive")
        if not np.isfinite(self.full_energy_sigma_keV) or self.full_energy_sigma_keV < 0.0:
            raise ValueError("full_energy_sigma_keV must be finite and non-negative")
        if weights[SpectrumComponent.DOUBLE_WALL] > 0.0 and self.double_wall is None:
            raise ValueError("positive double-wall weight requires component parameters")
        components = {
            "proton_wall": self.proton_wall,
            "triton_wall": self.triton_wall,
            "double_wall": self.double_wall,
        }
        for name, parameters in components.items():
            if parameters is None:
                continue
            minimum, maximum, alpha, beta = parameters
            values = np.asarray([minimum, maximum, alpha, beta], dtype=np.float64)
            if np.any(~np.isfinite(values)):
                raise ValueError(f"{name} parameters must be finite")
            if minimum < 0.0 or maximum <= minimum:
                raise ValueError(f"{name} energy domain is invalid")
            if alpha <= 0.0 or beta <= 0.0:
                raise ValueError(f"{name} Beta parameters must be positive")

    @classmethod
    def from_config(cls, config: EnergySpectrumConfig) -> ParametricHe3Spectrum:
        """Build a spectrum without substituting absent provisional parameters."""
        if config.provider != "parametric_he3":
            raise ValueError(f"unsupported Phase 1 spectrum provider: {config.provider}")
        weights = (
            _required(config.full_energy_fraction, "full_energy_fraction"),
            _required(config.proton_wall_fraction, "proton_wall_fraction"),
            _required(config.triton_wall_fraction, "triton_wall_fraction"),
            _required(config.double_wall_fraction, "double_wall_fraction"),
        )
        double_wall = None
        if weights[SpectrumComponent.DOUBLE_WALL] > 0.0:
            double_wall = (
                _required(config.double_wall_min_keV, "double_wall_min_keV"),
                _required(config.double_wall_max_keV, "double_wall_max_keV"),
                _required(config.double_wall_alpha, "double_wall_alpha"),
                _required(config.double_wall_beta, "double_wall_beta"),
            )
        return cls(
            full_energy_keV=_required(config.full_energy_keV, "full_energy_keV"),
            full_energy_sigma_keV=_required(config.full_energy_sigma_keV, "full_energy_sigma_keV"),
            weights=weights,
            proton_wall=(
                _required(config.proton_wall_min_keV, "proton_wall_min_keV"),
                _required(config.proton_wall_max_keV, "proton_wall_max_keV"),
                _required(config.proton_wall_alpha, "proton_wall_alpha"),
                _required(config.proton_wall_beta, "proton_wall_beta"),
            ),
            triton_wall=(
                _required(config.triton_wall_min_keV, "triton_wall_min_keV"),
                _required(config.triton_wall_max_keV, "triton_wall_max_keV"),
                _required(config.triton_wall_alpha, "triton_wall_alpha"),
                _required(config.triton_wall_beta, "triton_wall_beta"),
            ),
            double_wall=double_wall,
        )

    def sample(self, n: int, rng: np.random.Generator) -> SpectrumSamples:
        """Sample positive energies and stable component identifiers."""
        if n < 0:
            raise ValueError("n must be non-negative")
        component_id = rng.choice(4, size=n, p=self.weights).astype(np.int16, copy=False)
        energies_keV = np.empty(n, dtype=np.float64)

        full_mask = component_id == SpectrumComponent.FULL_ENERGY
        full_count = int(np.count_nonzero(full_mask))
        if full_count:
            if self.full_energy_sigma_keV == 0.0:
                full_samples = np.full(full_count, self.full_energy_keV, dtype=np.float64)
            else:
                full_samples = rng.normal(
                    self.full_energy_keV, self.full_energy_sigma_keV, size=full_count
                )
                for _ in range(MAX_TRUNCATION_RESAMPLES):
                    invalid = full_samples <= 0.0
                    if not np.any(invalid):
                        break
                    full_samples[invalid] = rng.normal(
                        self.full_energy_keV,
                        self.full_energy_sigma_keV,
                        size=int(np.count_nonzero(invalid)),
                    )
                if np.any(full_samples <= 0.0):
                    raise RuntimeError("failed to sample a positive full-energy peak")
            energies_keV[full_mask] = full_samples

        for component, parameters in (
            (SpectrumComponent.PROTON_WALL, self.proton_wall),
            (SpectrumComponent.TRITON_WALL, self.triton_wall),
            (SpectrumComponent.DOUBLE_WALL, self.double_wall),
        ):
            if parameters is None:
                continue
            mask = component_id == component
            count = int(np.count_nonzero(mask))
            if count:
                minimum, maximum, alpha, beta = parameters
                unit_samples = rng.beta(alpha, beta, size=count)
                energies_keV[mask] = minimum + (maximum - minimum) * unit_samples

        if np.any(~np.isfinite(energies_keV)) or np.any(energies_keV < 0.0):
            raise RuntimeError("spectrum produced an invalid energy")
        return SpectrumSamples(energy_dep_keV=energies_keV, component_id=component_id)
