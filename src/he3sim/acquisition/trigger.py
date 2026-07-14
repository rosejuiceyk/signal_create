"""Stateful positive/negative threshold trigger with hysteresis and hold time."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class TriggerState:
    """Cross-block trigger state in global sample coordinates."""

    next_sample_index: int = 0
    armed: bool = True
    pending_start_index: int = -1
    pending_count: int = 0


class ThresholdTrigger:
    """Detect one candidate per hysteretic threshold excursion."""

    def __init__(
        self,
        sample_rate_hz: float,
        polarity: int,
        threshold_V: float,
        hysteresis_V: float,
        min_hold_s: float,
    ) -> None:
        """Validate and precompute sample-domain trigger parameters."""
        if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
            raise ValueError("sample_rate_hz must be finite and positive")
        if polarity not in {-1, 1}:
            raise ValueError("trigger polarity must be -1 or 1")
        values = (threshold_V, hysteresis_V, min_hold_s)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("trigger parameters must be finite")
        aligned_threshold = polarity * threshold_V
        if aligned_threshold <= 0.0:
            raise ValueError("threshold sign must match trigger polarity")
        if hysteresis_V < 0.0 or hysteresis_V >= aligned_threshold:
            raise ValueError("hysteresis_V must be non-negative and below threshold magnitude")
        if min_hold_s < 0.0:
            raise ValueError("min_hold_s must be non-negative")
        self.sample_rate_hz = sample_rate_hz
        self.polarity = polarity
        self.aligned_threshold_V = aligned_threshold
        self.rearm_level_V = aligned_threshold - hysteresis_V
        self.hold_samples = max(1, math.ceil(min_hold_s * sample_rate_hz))

    def process_block(
        self,
        samples_V: npt.ArrayLike,
        sample_start: int,
        state: TriggerState | None = None,
    ) -> tuple[npt.NDArray[np.int64], TriggerState]:
        """Process a contiguous block and return global candidate sample indices."""
        samples = np.asarray(samples_V, dtype=np.float64)
        if samples.ndim != 1 or np.any(~np.isfinite(samples)):
            raise ValueError("trigger samples must be a finite vector")
        current = state or TriggerState()
        if sample_start != current.next_sample_index:
            raise ValueError("trigger blocks must be contiguous and ordered")
        aligned = self.polarity * samples
        armed = current.armed
        pending_start = current.pending_start_index
        pending_count = current.pending_count
        candidates: list[int] = []
        for local_index, value in enumerate(aligned):
            global_index = sample_start + local_index
            if not armed:
                if value <= self.rearm_level_V:
                    armed = True
                continue
            if pending_count:
                if value >= self.aligned_threshold_V:
                    pending_count += 1
                    if pending_count >= self.hold_samples:
                        candidates.append(pending_start)
                        armed = False
                        pending_start = -1
                        pending_count = 0
                else:
                    pending_start = -1
                    pending_count = 0
                continue
            if value >= self.aligned_threshold_V:
                pending_start = global_index
                pending_count = 1
                if self.hold_samples == 1:
                    candidates.append(pending_start)
                    armed = False
                    pending_start = -1
                    pending_count = 0
        next_state = TriggerState(
            next_sample_index=sample_start + samples.size,
            armed=armed,
            pending_start_index=pending_start,
            pending_count=pending_count,
        )
        return np.asarray(candidates, dtype=np.int64), next_state
