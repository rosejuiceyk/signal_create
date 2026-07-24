from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from he3sim.config import ParameterStatus
from he3sim.types import (
    EVENT_LINEAGE_DTYPE,
    OBSERVED_EVENT_DTYPE,
    TRUE_EVENT_DTYPE,
    CalibrationMetadata,
    Polarity,
    TrueEvent,
)


def test_true_event_is_immutable_and_keeps_polarity_separate() -> None:
    event = TrueEvent(
        event_id=1,
        t_s=0.25,
        energy_dep_keV=764.0,
        spectrum_component_id=0,
        amplitude_peak_V=0.1,
        tau_r_s=1.0e-6,
        tau_d_s=1.0e-5,
        polarity=Polarity.NEGATIVE,
        block_id=0,
        sample_index=10,
        pileup_group_id=-1,
        parameter_status=ParameterStatus.SYNTHETIC_DEMO,
    )

    assert event.amplitude_peak_V > 0.0
    assert event.polarity is Polarity.NEGATIVE
    with pytest.raises(FrozenInstanceError):
        event.event_id = 2  # type: ignore[misc]


def test_structured_dtypes_include_required_fields() -> None:
    assert TRUE_EVENT_DTYPE.names == (
        "event_id",
        "t_s",
        "energy_dep_keV",
        "spectrum_component_id",
        "amplitude_peak_V",
        "tau_r_s",
        "tau_d_s",
        "polarity",
        "block_id",
        "sample_index",
        "pileup_group_id",
        "parameter_status",
    )
    assert OBSERVED_EVENT_DTYPE.names is not None
    assert "trigger_time_s" in OBSERVED_EVENT_DTYPE.names
    assert "rise_time_10_90_s" in OBSERVED_EVENT_DTYPE.names
    assert "is_saturated" in OBSERVED_EVENT_DTYPE.names
    assert EVENT_LINEAGE_DTYPE.names == ("event_id", "chain_id", "generation")


def test_calibration_metadata_freezes_units_mapping() -> None:
    source_units = {"t_s": "s", "amplitude_peak_V": "V"}
    metadata = CalibrationMetadata(
        config_hash="a" * 64,
        code_version="0+unknown",
        seed=1,
        parameter_status=ParameterStatus.PROVISIONAL,
        units=source_units,
    )
    source_units["t_s"] = "ms"

    assert metadata.units["t_s"] == "s"
    with pytest.raises(TypeError):
        metadata.units["new"] = "unit"  # type: ignore[index]

    serialized = metadata.to_serializable_dict()
    assert serialized["parameter_status"] == "provisional"
    assert serialized["units"] == {"t_s": "s", "amplitude_peak_V": "V"}
    json.dumps(serialized)


def test_dtype_can_allocate_empty_tables_without_events() -> None:
    assert np.empty(0, dtype=TRUE_EVENT_DTYPE).size == 0
    assert np.empty(0, dtype=OBSERVED_EVENT_DTYPE).size == 0
