"""Isolated sampled-pulse feature extraction for Phase 2 validation."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class PulseFeatures:
    """Peak, signed time integral, and sampled 10%-90% timing features."""

    peak_V: float
    integral_V_s: float
    rise_time_10_90_s: float
    fall_time_90_10_s: float
    peak_sample_index: int


def _crossing_time_s(
    signal: npt.NDArray[np.float64],
    threshold: float,
    sample_rate_hz: float,
    start: int,
    stop: int,
    rising: bool,
) -> float:
    """Interpolate the first threshold crossing in an inclusive index interval."""
    for right in range(max(1, start), stop + 1):
        left_value = float(signal[right - 1])
        right_value = float(signal[right])
        crossed = right_value >= threshold if rising else right_value <= threshold
        previously_outside = left_value < threshold if rising else left_value > threshold
        if crossed and previously_outside:
            fraction = (threshold - left_value) / (right_value - left_value)
            return (right - 1 + fraction) / sample_rate_hz
    raise ValueError("sample window does not contain the requested threshold crossing")


def extract_pulse_features(
    samples_V: npt.ArrayLike,
    sample_rate_hz: float,
    polarity: int,
    baseline_V: float = 0.0,
) -> PulseFeatures:
    """Measure one isolated pulse without treating model constants as rise/fall times."""
    samples = np.asarray(samples_V, dtype=np.float64)
    if samples.ndim != 1 or samples.size < 3 or np.any(~np.isfinite(samples)):
        raise ValueError("samples_V must be a finite one-dimensional array with at least 3 samples")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("sample_rate_hz must be finite and positive")
    if polarity not in {-1, 1}:
        raise ValueError("polarity must be -1 or 1")
    if not math.isfinite(baseline_V):
        raise ValueError("baseline_V must be finite")

    centered = samples - baseline_V
    aligned = polarity * centered
    peak_index = int(np.argmax(aligned))
    peak_magnitude_V = float(aligned[peak_index])
    if peak_magnitude_V <= 0.0 or peak_index == 0 or peak_index >= samples.size - 1:
        raise ValueError("sample window must contain a positive isolated pulse peak and both tails")

    rise_10_s = _crossing_time_s(
        aligned,
        0.1 * peak_magnitude_V,
        sample_rate_hz,
        1,
        peak_index,
        True,
    )
    rise_90_s = _crossing_time_s(
        aligned,
        0.9 * peak_magnitude_V,
        sample_rate_hz,
        1,
        peak_index,
        True,
    )
    fall_90_s = _crossing_time_s(
        aligned,
        0.9 * peak_magnitude_V,
        sample_rate_hz,
        peak_index + 1,
        samples.size - 1,
        False,
    )
    fall_10_s = _crossing_time_s(
        aligned,
        0.1 * peak_magnitude_V,
        sample_rate_hz,
        peak_index + 1,
        samples.size - 1,
        False,
    )
    integral_V_s = float(
        np.sum((centered[:-1] + centered[1:]) * (0.5 / sample_rate_hz), dtype=np.float64)
    )
    return PulseFeatures(
        peak_V=polarity * peak_magnitude_V,
        integral_V_s=integral_V_s,
        rise_time_10_90_s=rise_90_s - rise_10_s,
        fall_time_90_10_s=fall_10_s - fall_90_s,
        peak_sample_index=peak_index,
    )
