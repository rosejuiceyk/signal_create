"""MCNP spectrum-import contract and an intentionally unavailable Phase 0 stub."""

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
        """Reject MCNP import during Phase 0."""
        raise NotImplementedError(f"MCNP import is not implemented in Phase 0: {path}")
