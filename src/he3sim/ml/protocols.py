"""Public research interfaces for Phase 5 event generators."""

from __future__ import annotations

from typing import Protocol

import numpy as np
import numpy.typing as npt


class ConditionalMarkedEventGenerator(Protocol):
    """Generate one bounded variable-length marked event sequence."""

    def generate(
        self,
        true_rate_cps: float,
        window_duration_s: float,
        *,
        seed: int,
        max_events: int,
    ) -> npt.NDArray[np.void]:
        """Sample ordered truth events conditioned on rate, duration, config, and seed."""
        ...
