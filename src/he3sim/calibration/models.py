"""Typed Phase 4Q records that do not imply calibrated physical units."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt


class WaveformVariant(StrEnum):
    """Explicit acquisition-file waveform versions."""

    RAW = "RAW"
    FILTERED = "FILTERED"
    UNFILTERED = "UNFILTERED"


class QCStatus(StrEnum):
    """Four-state result that prevents missing evidence from becoming a pass."""

    PASS = "pass"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"
    UNKNOWN = "unknown"


class LabelStatus(StrEnum):
    """Allowed label confidence before independent particle truth exists."""

    UNKNOWN = "unknown"
    CANDIDATE = "candidate"


class SamplingAxisStatus(StrEnum):
    """Evidence state for exported-sample timing semantics."""

    UNCONFIRMED = "unconfirmed"
    CONFIRMED_NATIVE = "confirmed_native"
    CONFIRMED_DEDUPLICATED = "confirmed_deduplicated"


class RunUsability(StrEnum):
    """Conservative run-level qualification categories."""

    EMPTY = "empty"
    INVENTORY_ONLY = "inventory_only"
    QC_LIMITED = "qc_limited"
    CALIBRATION_CANDIDATE = "calibration_candidate"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class WaveformRecord:
    """One exported event row with raw metadata and integer ADC-like samples."""

    event_index: int
    source_path: Path
    variant: WaveformVariant
    metadata: dict[str, str]
    samples_ADC_counts: npt.NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class DuplicateMetrics:
    """Index-domain evidence for repeated adjacent exported values."""

    exported_sample_count: int
    candidate_deduplicated_sample_count: int
    even_pair_equal_fraction: float
    odd_pair_equal_fraction: float
    lag1_equal_fraction: float

    def to_dict(self) -> dict[str, int | float]:
        """Return a JSON-compatible representation."""
        return {
            "exported_sample_count": self.exported_sample_count,
            "candidate_deduplicated_sample_count": self.candidate_deduplicated_sample_count,
            "even_pair_equal_fraction": self.even_pair_equal_fraction,
            "odd_pair_equal_fraction": self.odd_pair_equal_fraction,
            "lag1_equal_fraction": self.lag1_equal_fraction,
        }


@dataclass(frozen=True, slots=True)
class EventQCResult:
    """Per-event Phase 4Q metrics and explicit QC decisions."""

    metrics: dict[str, int | float | None]
    statuses: dict[str, QCStatus]
    reasons: dict[str, str]
    duplicate_metrics: DuplicateMetrics

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""
        return {
            "metrics": self.metrics,
            "qc": {name: status.value for name, status in self.statuses.items()},
            "qc_reasons": dict(self.reasons),
            "duplicate_metrics": self.duplicate_metrics.to_dict(),
        }
