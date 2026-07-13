"""DT5800 adapter contract with no SDK or hardware implementation."""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np
import numpy.typing as npt


class DT5800Adapter(Protocol):
    """Future adapter for sending digital samples to a DT5800 device."""

    def send(self, samples: npt.NDArray[np.signedinteger[Any]]) -> None:
        """Send samples to hardware."""
        ...


class DT5800Stub:
    """Explicit non-implementation that has no vendor SDK dependency."""

    def send(self, samples: npt.NDArray[np.signedinteger[Any]]) -> None:
        """Reject hardware access during the offline prototype phases."""
        raise NotImplementedError(
            f"DT5800 hardware control is outside Phase 0 (received {samples.size} samples)"
        )
