"""Peak-normalized double-exponential pulse mathematics for Phase 2."""

from __future__ import annotations

import math
import warnings
from typing import Final

import numpy as np
import numpy.typing as npt

MIN_RESOLVED_TIME_CONSTANT_SAMPLES: Final[float] = 2.0


class PulseResolutionWarning(UserWarning):
    """Warn that configured model time constants are poorly sampled."""


def validate_time_constants(tau_r_s: float, tau_d_s: float) -> None:
    """Require finite double-exponential time constants with ``tau_d > tau_r > 0``."""
    if not math.isfinite(tau_r_s) or not math.isfinite(tau_d_s):
        raise ValueError("pulse time constants must be finite")
    if tau_r_s <= 0.0 or tau_d_s <= tau_r_s:
        raise ValueError("pulse time constants must satisfy tau_d_s > tau_r_s > 0")


def double_exponential_peak_time_s(tau_r_s: float, tau_d_s: float) -> float:
    """Return the analytic time from pulse onset to the continuous maximum."""
    validate_time_constants(tau_r_s, tau_d_s)
    return (tau_r_s * tau_d_s / (tau_d_s - tau_r_s)) * math.log(tau_d_s / tau_r_s)


def double_exponential_peak_value(tau_r_s: float, tau_d_s: float) -> float:
    """Return the positive unnormalized kernel value at its analytic maximum."""
    peak_time_s = double_exponential_peak_time_s(tau_r_s, tau_d_s)
    return math.exp(-peak_time_s / tau_d_s) - math.exp(-peak_time_s / tau_r_s)


def normalized_double_exponential(
    delay_s: float | npt.NDArray[np.float64],
    tau_r_s: float,
    tau_d_s: float,
) -> float | npt.NDArray[np.float64]:
    """Evaluate the causal continuous kernel whose analytic peak is one."""
    validate_time_constants(tau_r_s, tau_d_s)
    delays = np.asarray(delay_s, dtype=np.float64)
    values = np.zeros_like(delays)
    causal = delays >= 0.0
    if np.any(causal):
        causal_delays = delays[causal]
        raw = np.exp(-causal_delays / tau_d_s) - np.exp(-causal_delays / tau_r_s)
        values[causal] = raw / double_exponential_peak_value(tau_r_s, tau_d_s)
    if np.ndim(delay_s) == 0:
        return float(values)
    return values


def discrete_peak_raw_value(
    event_time_s: float,
    sample_rate_hz: float,
    tau_r_s: float,
    tau_d_s: float,
    grid_origin_s: float = 0.0,
) -> float:
    """Return the largest raw kernel value available on one uniform sample grid."""
    validate_time_constants(tau_r_s, tau_d_s)
    if not math.isfinite(event_time_s) or not math.isfinite(grid_origin_s):
        raise ValueError("event time and grid origin must be finite")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("sample_rate_hz must be finite and positive")

    onset_index = math.ceil((event_time_s - grid_origin_s) * sample_rate_hz)
    continuous_peak_index = (
        event_time_s - grid_origin_s + double_exponential_peak_time_s(tau_r_s, tau_d_s)
    ) * sample_rate_hz
    candidates = {
        onset_index,
        max(onset_index, math.floor(continuous_peak_index)),
        max(onset_index, math.ceil(continuous_peak_index)),
    }
    raw_values = []
    for sample_index in candidates:
        delay_s = grid_origin_s + sample_index / sample_rate_hz - event_time_s
        if delay_s >= 0.0:
            raw_values.append(math.exp(-delay_s / tau_d_s) - math.exp(-delay_s / tau_r_s))
    maximum = max(raw_values, default=0.0)
    if not math.isfinite(maximum) or maximum <= 0.0:
        raise ValueError("sample grid cannot represent a positive double-exponential peak")
    return maximum


def warn_if_time_constants_under_resolved(
    sample_rate_hz: float,
    tau_r_s: float,
    tau_d_s: float,
) -> None:
    """Warn when either model time constant spans fewer than two samples."""
    validate_time_constants(tau_r_s, tau_d_s)
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("sample_rate_hz must be finite and positive")
    rise_samples = tau_r_s * sample_rate_hz
    decay_samples = tau_d_s * sample_rate_hz
    if min(rise_samples, decay_samples) < MIN_RESOLVED_TIME_CONSTANT_SAMPLES:
        warnings.warn(
            "pulse time constants are under-resolved at the configured sample rate: "
            f"tau_r={rise_samples:.3g} samples, tau_d={decay_samples:.3g} samples",
            PulseResolutionWarning,
            stacklevel=2,
        )
