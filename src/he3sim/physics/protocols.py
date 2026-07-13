"""Protocols that preserve future physics extension points without implementation."""

from __future__ import annotations

from typing import Protocol

import numpy as np
import numpy.typing as npt


class RateProfile(Protocol):
    """Return a true arrival rate in counts per second at time ``t_s``."""

    def rate(self, t_s: float | npt.NDArray[np.float64]) -> float | npt.NDArray[np.float64]:
        """Evaluate the rate profile."""
        ...


class EventArrivalGenerator(Protocol):
    """Contract for future truth-layer arrival samplers."""

    def sample(
        self,
        profile: RateProfile,
        t_start_s: float,
        duration_s: float,
        rng: np.random.Generator,
    ) -> npt.NDArray[np.float64]:
        """Return sorted event times; no implementation exists in Phase 0."""
        ...


class EnergySpectrumProvider(Protocol):
    """Contract for future deposited-energy providers."""

    def sample(self, n: int, rng: np.random.Generator) -> npt.NDArray[np.float64]:
        """Return deposited energies in keV; no implementation exists in Phase 0."""
        ...


class RecoveryModel(Protocol):
    """Contract for a future calibrated electronics recovery model."""

    def reset(self) -> None:
        """Reset future recovery state at an explicit run boundary."""
        ...

    def process(
        self,
        samples_V: npt.NDArray[np.float64],
        sample_rate_hz: float,
    ) -> npt.NDArray[np.float64]:
        """Process a bounded block; no recovery implementation exists in Phase 0."""
        ...
