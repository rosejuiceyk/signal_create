"""Post-inference constraints and pure-physics fallback for Phase 6S."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class GuardedWaveform:
    """One correction result with an explicit fallback decision."""

    waveform_V: npt.NDArray[np.float32]
    accepted: bool
    fallback_reason: str | None


def apply_residual_with_guard(
    physical_waveform_V: npt.NDArray[np.float32],
    predicted_residual_V: npt.NDArray[np.float32],
    event_guard_mask: npt.NDArray[np.bool_],
    max_abs_residual_V: float,
    *,
    event_tolerance_V: float = 1.0e-8,
) -> GuardedWaveform:
    """Apply a residual only when shape, finiteness, amplitude, and event guards pass."""
    physical = np.asarray(physical_waveform_V, dtype=np.float32)
    residual = np.asarray(predicted_residual_V, dtype=np.float32)
    guard = np.asarray(event_guard_mask, dtype=np.bool_)
    reason: str | None = None
    if physical.ndim != 1 or residual.shape != physical.shape or guard.shape != physical.shape:
        reason = "shape_mismatch"
    elif not np.all(np.isfinite(physical)) or not np.all(np.isfinite(residual)):
        reason = "non_finite"
    elif float(np.max(np.abs(residual), initial=0.0)) > max_abs_residual_V * (1.0 + 1.0e-6):
        reason = "residual_limit"
    elif np.any(np.abs(residual[guard]) > event_tolerance_V):
        reason = "event_guard_violation"
    if reason is not None:
        return GuardedWaveform(physical.copy(), False, reason)
    return GuardedWaveform(np.asarray(physical + residual, dtype=np.float32), True, None)
