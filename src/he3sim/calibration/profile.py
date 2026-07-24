"""Strict YAML profiles for vendor-specific acquisition exports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import Field, model_validator

from he3sim.calibration.models import WaveformVariant
from he3sim.config import ConfigModel, ParameterStatus


class VariantProfile(ConfigModel):
    """Directory and filename rule for one waveform version."""

    directory: str = Field(min_length=1)
    file_glob: str = Field(min_length=1)


class QCThresholdProfile(ConfigModel):
    """Explicit provisional index-domain QC thresholds."""

    parameter_status: ParameterStatus
    source: str = Field(min_length=1)
    baseline_fraction: float = Field(gt=0.0, le=0.4)
    tail_fraction: float = Field(gt=0.0, le=0.4)
    baseline_drift_sigma: float = Field(gt=0.0)
    low_amplitude_snr: float = Field(gt=0.0)
    tail_return_peak_fraction: float = Field(gt=0.0, lt=1.0)
    ringing_peak_fraction: float = Field(gt=0.0, lt=1.0)
    ringing_min_alternations: int = Field(ge=1)
    duplicate_pair_fraction: float = Field(gt=0.0, le=1.0)
    trigger_fraction: float = Field(gt=0.0, lt=1.0)
    min_pretrigger_exported_samples: int = Field(ge=1)
    adc_min_count: int | None = None
    adc_max_count: int | None = None

    @model_validator(mode="after")
    def validate_adc_limits(self) -> QCThresholdProfile:
        """Require either two ordered ADC rails or neither rail."""
        if (self.adc_min_count is None) != (self.adc_max_count is None):
            raise ValueError("adc_min_count and adc_max_count must be configured together")
        if (
            self.adc_min_count is not None
            and self.adc_max_count is not None
            and self.adc_min_count >= self.adc_max_count
        ):
            raise ValueError("adc_min_count must be smaller than adc_max_count")
        return self


class AcquisitionProfile(ConfigModel):
    """Complete read-only parsing contract for one acquisition export family."""

    profile_name: str = Field(min_length=1)
    parameter_status: ParameterStatus
    source: str = Field(min_length=1)
    run_glob: str = Field(min_length=1)
    csv_delimiter: str = Field(min_length=1, max_length=1)
    csv_encoding: str = Field(min_length=1)
    info_encoding: str = Field(min_length=1)
    samples_column: str = Field(min_length=1)
    metadata_columns: list[str] = Field(min_length=1)
    primary_variant: WaveformVariant
    variants: dict[WaveformVariant, VariantProfile]
    info_file_glob: str = Field(min_length=1)
    settings_file_glob: str = Field(min_length=1)
    info_patterns: dict[str, str]
    xml_tags: dict[str, str]
    xml_parameter_keys: dict[str, str]
    minimum_independent_runs_per_rate: int = Field(ge=3)
    qc: QCThresholdProfile

    @model_validator(mode="after")
    def validate_variants(self) -> AcquisitionProfile:
        """Require the primary variant and all three explicit version names."""
        required = set(WaveformVariant)
        if set(self.variants) != required:
            raise ValueError("variants must define RAW, FILTERED, and UNFILTERED")
        if self.primary_variant not in self.variants:
            raise ValueError("primary_variant must be present in variants")
        return self


def load_acquisition_profile(path: str | Path) -> AcquisitionProfile:
    """Load one strict acquisition profile without inferring missing fields."""
    profile_path = Path(path)
    payload = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("acquisition profile must contain a YAML mapping")
    return AcquisitionProfile.model_validate(payload)


def acquisition_profile_hash(profile: AcquisitionProfile) -> str:
    """Return a deterministic SHA-256 hash of the normalized profile."""
    encoded = json.dumps(
        profile.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
