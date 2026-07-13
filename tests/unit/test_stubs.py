from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from he3sim.io.dt5800_stub import DT5800Stub
from he3sim.io.mcnp import MCNPSpectrumImporterStub
from he3sim.io.oscilloscope import OscilloscopeImporterStub


def test_external_adapters_are_explicit_phase0_stubs() -> None:
    with pytest.raises(NotImplementedError, match="MCNP"):
        MCNPSpectrumImporterStub().load(Path("spectrum.txt"))
    with pytest.raises(NotImplementedError, match="oscilloscope"):
        OscilloscopeImporterStub().load(Path("scope.csv"), "generic_csv")
    with pytest.raises(NotImplementedError, match="DT5800"):
        DT5800Stub().send(np.array([0, 1], dtype=np.int16))
