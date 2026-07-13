"""Typed records and NumPy dtypes shared by future simulation stages."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from types import MappingProxyType
from typing import Any

import numpy as np
import numpy.typing as npt

from he3sim.config import ParameterStatus

FloatArray = npt.NDArray[np.float32]
IntegerArray = npt.NDArray[np.signedinteger[Any]]
BooleanArray = npt.NDArray[np.bool_]


class Polarity(IntEnum):
    """Pulse polarity stored independently from positive peak magnitude."""

    NEGATIVE = -1
    POSITIVE = 1


class RejectionReason(StrEnum):
    """Reserved observation-layer rejection categories."""

    NONE = "none"
    DEAD_TIME = "dead_time"
    BELOW_THRESHOLD = "below_threshold"
    SATURATED = "saturated"


@dataclass(frozen=True, slots=True)
class TrueEvent:
    """One truth-layer event record; Phase 0 defines but never generates it."""

    event_id: int
    t_s: float
    energy_dep_keV: float
    spectrum_component_id: int
    amplitude_peak_V: float
    tau_r_s: float
    tau_d_s: float
    polarity: Polarity
    block_id: int
    sample_index: int
    pileup_group_id: int
    parameter_status: ParameterStatus


@dataclass(frozen=True, slots=True)
class WaveformBlock:
    """Metadata and optional arrays for one future continuous-waveform block."""

    block_id: int
    t_start_s: float
    sample_rate_hz: float
    analog_samples_V: FloatArray | None = None
    adc_samples: IntegerArray | None = None
    saturation_mask: BooleanArray | None = None


@dataclass(frozen=True, slots=True)
class ObservedEvent:
    """One observation-layer event record after future triggering and dead time."""

    trigger_id: int
    trigger_time_s: float
    accepted: bool
    rejection_reason: RejectionReason
    peak_adc: int
    peak_V: float
    integral_V_s: float
    rise_time_10_90_s: float
    fall_time_90_10_s: float
    is_pileup: bool
    is_saturated: bool


@dataclass(frozen=True, slots=True)
class CalibrationMetadata:
    """Serializable provenance required alongside future calibrated outputs."""

    config_hash: str
    code_version: str
    seed: int
    parameter_status: ParameterStatus
    units: Mapping[str, str]
    source: str | None = None

    def __post_init__(self) -> None:
        """Freeze a defensive copy of the units mapping."""
        object.__setattr__(self, "units", MappingProxyType(dict(self.units)))

    def to_serializable_dict(self) -> dict[str, int | str | dict[str, str] | None]:
        """Return JSON-compatible calibration provenance without mutable aliases."""
        return {
            "config_hash": self.config_hash,
            "code_version": self.code_version,
            "seed": self.seed,
            "parameter_status": self.parameter_status.value,
            "units": dict(self.units),
            "source": self.source,
        }


TRUE_EVENT_DTYPE = np.dtype(
    [
        ("event_id", "<i8"),
        ("t_s", "<f8"),
        ("energy_dep_keV", "<f8"),
        ("spectrum_component_id", "<i2"),
        ("amplitude_peak_V", "<f8"),
        ("tau_r_s", "<f8"),
        ("tau_d_s", "<f8"),
        ("polarity", "i1"),
        ("block_id", "<i8"),
        ("sample_index", "<i8"),
        ("pileup_group_id", "<i8"),
        ("parameter_status", "S16"),
    ]
)
"""Structured dtype for future bulk truth-event storage."""


OBSERVED_EVENT_DTYPE = np.dtype(
    [
        ("trigger_id", "<i8"),
        ("trigger_time_s", "<f8"),
        ("accepted", "?"),
        ("rejection_reason", "S32"),
        ("peak_adc", "<i8"),
        ("peak_V", "<f8"),
        ("integral_V_s", "<f8"),
        ("rise_time_10_90_s", "<f8"),
        ("fall_time_90_10_s", "<f8"),
        ("is_pileup", "?"),
        ("is_saturated", "?"),
    ]
)
"""Structured dtype for future bulk observed-event storage."""
