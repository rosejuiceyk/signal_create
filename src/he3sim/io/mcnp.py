"""MCNP spectrum-import contract and an intentionally unavailable stub."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np
import numpy.typing as npt


class MCNPSpectrumImporter(Protocol):
    """Future adapter for event lists or normalized energy histograms."""

    def load(self, path: Path) -> npt.NDArray[np.float64]:
        """Load deposited energies in keV."""
        ...


class MCNPSpectrumImporterStub:
    """Explicit non-implementation used until the MCNP integration phase."""

    def load(self, path: Path) -> npt.NDArray[np.float64]:
        """Reject MCNP import through Phase 1."""
        raise NotImplementedError(f"MCNP import is not implemented through Phase 1: {path}")
