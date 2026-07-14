"""Ideal and trigger-candidate dead-time filters for the observation layer."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from he3sim.config import DeadTimeMode


@dataclass(frozen=True, slots=True)
class DeadTimeResult:
    """Acceptance mask and final busy boundary for ordered candidates."""

    accepted: npt.NDArray[np.bool_]
    busy_until_s: float


def apply_dead_time(
    candidate_times_s: npt.ArrayLike,
    duration_s: float,
    mode: DeadTimeMode,
) -> DeadTimeResult:
    """Apply ideal dead time without changing the input candidate stream."""
    times = np.asarray(candidate_times_s, dtype=np.float64)
    if times.ndim != 1 or np.any(~np.isfinite(times)) or np.any(times < 0.0):
        raise ValueError("candidate times must be a finite non-negative vector")
    if times.size > 1 and np.any(np.diff(times) <= 0.0):
        raise ValueError("candidate times must be strictly increasing")
    if not math.isfinite(duration_s) or duration_s < 0.0:
        raise ValueError("dead-time duration must be finite and non-negative")
    if mode is DeadTimeMode.NONE:
        if duration_s != 0.0:
            raise ValueError("dead-time mode none requires zero duration")
        return DeadTimeResult(np.ones(times.size, dtype=np.bool_), 0.0)
    if duration_s <= 0.0:
        raise ValueError("enabled dead-time mode requires positive duration")

    accepted = np.zeros(times.size, dtype=np.bool_)
    busy_until_s = -math.inf
    for index, candidate_s in enumerate(times):
        if candidate_s >= busy_until_s:
            accepted[index] = True
            busy_until_s = float(candidate_s + duration_s)
        elif mode is DeadTimeMode.PARALYZABLE:
            busy_until_s = float(candidate_s + duration_s)
    return DeadTimeResult(accepted, busy_until_s)


def theoretical_observed_rate_cps(
    true_rate_cps: float,
    duration_s: float,
    mode: DeadTimeMode,
) -> float:
    """Return the ideal homogeneous-Poisson dead-time rate relation."""
    if not math.isfinite(true_rate_cps) or true_rate_cps < 0.0:
        raise ValueError("true_rate_cps must be finite and non-negative")
    if not math.isfinite(duration_s) or duration_s < 0.0:
        raise ValueError("dead-time duration must be finite and non-negative")
    if mode is DeadTimeMode.NONE:
        return true_rate_cps
    if mode is DeadTimeMode.NONPARALYZABLE:
        return true_rate_cps / (1.0 + true_rate_cps * duration_s)
    return true_rate_cps * math.exp(-true_rate_cps * duration_s)
