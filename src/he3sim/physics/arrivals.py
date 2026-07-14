"""Exact homogeneous-Poisson arrival generators for Phase 1."""

from __future__ import annotations

from enum import StrEnum

import numpy as np
import numpy.typing as npt

from he3sim.physics.protocols import EventArrivalGenerator, RateProfile
from he3sim.physics.rate_profiles import ConstantRateProfile

DEFAULT_INTERVAL_CHUNK_SIZE = 65_536
MIN_INTERVAL_CHUNK_SIZE = 64


class ArrivalAlgorithm(StrEnum):
    """Available exact homogeneous-Poisson sampling algorithms."""

    POISSON_UNIFORM = "poisson_uniform"
    CUMULATIVE_EXPONENTIAL = "cumulative_exponential"


def _validate_inputs(
    profile: RateProfile,
    t_start_s: float,
    duration_s: float,
) -> ConstantRateProfile:
    """Validate the Phase 1 constant-rate window and return its concrete profile."""
    if not isinstance(profile, ConstantRateProfile):
        raise TypeError("Phase 1 arrival generators require ConstantRateProfile")
    if not np.isfinite(t_start_s):
        raise ValueError("t_start_s must be finite")
    if not np.isfinite(duration_s) or duration_s <= 0.0:
        raise ValueError("duration_s must be finite and positive")
    t_end_s = t_start_s + duration_s
    if not np.isfinite(t_end_s):
        raise ValueError("arrival window end must be finite")
    if t_end_s <= t_start_s:
        raise ValueError("arrival window must be representable with positive width")
    return profile


def _validate_result(
    times_s: npt.NDArray[np.float64],
    t_start_s: float,
    duration_s: float,
) -> npt.NDArray[np.float64]:
    """Enforce finite, in-window, strictly increasing event times."""
    if times_s.ndim != 1:
        raise RuntimeError("arrival generator returned a non-vector result")
    if times_s.size:
        if not np.all(np.isfinite(times_s)):
            raise RuntimeError("arrival generator returned non-finite times")
        if times_s[0] < t_start_s or times_s[-1] >= t_start_s + duration_s:
            raise RuntimeError("arrival generator returned an out-of-window time")
        if np.any(np.diff(times_s) <= 0.0):
            raise RuntimeError("arrival times are not strictly increasing")
    return times_s


class PoissonUniformArrivalGenerator:
    """Sample a Poisson count followed by sorted uniform event times."""

    def sample(
        self,
        profile: RateProfile,
        t_start_s: float,
        duration_s: float,
        rng: np.random.Generator,
    ) -> npt.NDArray[np.float64]:
        """Return exact homogeneous-Poisson event times in ``[start, end)``."""
        constant = _validate_inputs(profile, t_start_s, duration_s)
        count = int(rng.poisson(constant.rate_cps * duration_s))
        offsets_s = np.sort(rng.uniform(0.0, duration_s, size=count)).astype(np.float64, copy=False)
        return _validate_result(offsets_s + t_start_s, t_start_s, duration_s)


class CumulativeExponentialArrivalGenerator:
    """Sample cumulative exponential intervals in bounded vectorized chunks."""

    def __init__(self, chunk_size: int = DEFAULT_INTERVAL_CHUNK_SIZE) -> None:
        """Configure the bounded temporary interval chunk size."""
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self.chunk_size = chunk_size

    def sample(
        self,
        profile: RateProfile,
        t_start_s: float,
        duration_s: float,
        rng: np.random.Generator,
    ) -> npt.NDArray[np.float64]:
        """Return exact homogeneous-Poisson event times in ``[start, end)``."""
        constant = _validate_inputs(profile, t_start_s, duration_s)
        scale_s = 1.0 / constant.rate_cps
        elapsed_s = 0.0
        chunks: list[npt.NDArray[np.float64]] = []

        while True:
            remaining_expected = constant.rate_cps * (duration_s - elapsed_s)
            adaptive_size = int(
                np.ceil(remaining_expected + 10.0 * np.sqrt(remaining_expected + 1.0) + 16.0)
            )
            draw_size = min(self.chunk_size, max(MIN_INTERVAL_CHUNK_SIZE, adaptive_size))
            intervals_s = rng.exponential(scale_s, size=draw_size)
            cumulative_s = elapsed_s + np.cumsum(intervals_s, dtype=np.float64)
            inside = cumulative_s < duration_s
            inside_count = int(np.count_nonzero(inside))
            if inside_count:
                chunks.append(cumulative_s[:inside_count])
            if inside_count < draw_size:
                break
            elapsed_s = float(cumulative_s[-1])

        offsets_s = np.concatenate(chunks) if chunks else np.empty(0, dtype=np.float64)
        return _validate_result(offsets_s + t_start_s, t_start_s, duration_s)


def arrival_generator_for(algorithm: ArrivalAlgorithm) -> EventArrivalGenerator:
    """Construct the selected Phase 1 arrival generator."""
    if algorithm is ArrivalAlgorithm.POISSON_UNIFORM:
        return PoissonUniformArrivalGenerator()
    if algorithm is ArrivalAlgorithm.CUMULATIVE_EXPONENTIAL:
        return CumulativeExponentialArrivalGenerator()
    raise ValueError(f"unsupported arrival algorithm: {algorithm}")
