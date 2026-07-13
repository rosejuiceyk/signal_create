"""Oscilloscope-import contract and an intentionally unavailable Phase 0 stub."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np
import numpy.typing as npt


class OscilloscopeImporter(Protocol):
    """Future profile-driven adapter for oscilloscope waveforms."""

    def load(self, path: Path, profile: str) -> npt.NDArray[np.float64]:
        """Load voltage samples according to an explicit profile."""
        ...


class OscilloscopeImporterStub:
    """Explicit non-implementation used until the calibration phase."""

    def load(self, path: Path, profile: str) -> npt.NDArray[np.float64]:
        """Reject oscilloscope import during Phase 0."""
        raise NotImplementedError(
            f"oscilloscope import is not implemented in Phase 0: {path} ({profile})"
        )
