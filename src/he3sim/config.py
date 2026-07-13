"""Validated configuration models and deterministic configuration hashing."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Generic, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")


class ConfigModel(BaseModel):
    """Base model that rejects unknown configuration keys."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        allow_inf_nan=False,
    )


class ParameterStatus(StrEnum):
    """Evidence status attached to configurable numerical parameters."""

    SYNTHETIC_DEMO = "synthetic_demo"
    PROVISIONAL = "provisional"
    VALIDATED = "validated"


class ParameterValue(ConfigModel, Generic[T]):
    """A value together with its evidence status and provenance."""

    value: T | None
    status: ParameterStatus
    source: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_evidence(self) -> ParameterValue[T]:
        """Require evidence and a value before a parameter can be validated."""
        if self.status is ParameterStatus.VALIDATED:
            if self.value is None:
                raise ValueError("validated parameters must have a value")
            if self.source is None or not self.source.strip():
                raise ValueError("validated parameters must identify an evidence source")
            if self.reviewed_by is None or not self.reviewed_by.strip():
                raise ValueError("validated parameters must identify a human reviewer")
            if self.reviewed_at is None or self.reviewed_at.tzinfo is None:
                raise ValueError("validated parameters must include a timezone-aware review time")
        if self.status is ParameterStatus.SYNTHETIC_DEMO and self.value is None:
            raise ValueError("synthetic_demo parameters must have a demonstration value")
        return self


class RunMetadataConfig(ConfigModel):
    """Run identity and reproducibility inputs."""

    run_name: str = Field(min_length=1)
    description: str = ""
    seed: ParameterValue[int]

    @model_validator(mode="after")
    def validate_seed(self) -> RunMetadataConfig:
        """Accept only non-negative seeds supported by NumPy SeedSequence."""
        if self.seed.value is not None and self.seed.value < 0:
            raise ValueError("seed must be non-negative")
        return self


class SimulationDomainConfig(ConfigModel):
    """Supported true-rate and sampling-rate operating inputs."""

    true_rate_cps: ParameterValue[float]
    sample_rate_hz: ParameterValue[float]

    @model_validator(mode="after")
    def validate_supported_domain(self) -> SimulationDomainConfig:
        """Enforce the project operating envelope when values are present."""
        rate = self.true_rate_cps.value
        sample_rate = self.sample_rate_hz.value
        if rate is not None and not 10.0 <= rate <= 1.0e7:
            raise ValueError("true_rate_cps must be within [10, 1e7]")
        if sample_rate is not None and not 100.0e6 <= sample_rate <= 250.0e6:
            raise ValueError("sample_rate_hz must be within [100e6, 250e6]")
        return self


class ObservationMode(StrEnum):
    """Method used to define the virtual observation horizon."""

    FIXED_DURATION = "fixed_duration"
    TARGET_EVENT_COUNT = "target_event_count"


class ObservationWindowConfig(ConfigModel):
    """Configuration for a fixed duration or a target event count."""

    mode: ObservationMode
    duration_s: ParameterValue[float] | None = None
    target_event_count: ParameterValue[int] | None = None

    @model_validator(mode="after")
    def validate_mode_fields(self) -> ObservationWindowConfig:
        """Require exactly the value selected by the observation mode."""
        if self.mode is ObservationMode.FIXED_DURATION:
            if self.duration_s is None or self.duration_s.value is None:
                raise ValueError("fixed_duration mode requires duration_s")
            if self.duration_s.value <= 0.0:
                raise ValueError("duration_s must be positive")
            if self.target_event_count is not None:
                raise ValueError("fixed_duration mode cannot set target_event_count")
        else:
            if self.target_event_count is None or self.target_event_count.value is None:
                raise ValueError("target_event_count mode requires target_event_count")
            if self.target_event_count.value <= 0:
                raise ValueError("target_event_count must be positive")
            if self.duration_s is not None:
                raise ValueError("target_event_count mode cannot set duration_s")
        return self


class EnergySpectrumConfig(ConfigModel):
    """Declarative placeholder for a future He-3 spectrum provider."""

    provider: str = "parametric_he3"
    full_energy_keV: ParameterValue[float]
    full_energy_fraction: ParameterValue[float]
    proton_wall_fraction: ParameterValue[float]
    triton_wall_fraction: ParameterValue[float]
    double_wall_fraction: ParameterValue[float]


class AmplitudeCalibrationConfig(ConfigModel):
    """Placeholder values for the future energy-to-peak calibration."""

    gain_V_per_keV: ParameterValue[float]
    offset_V: ParameterValue[float]
    spread_std_V: ParameterValue[float]
    polarity: ParameterValue[int]

    @model_validator(mode="after")
    def validate_amplitude_fields(self) -> AmplitudeCalibrationConfig:
        """Validate signs and polarity without performing amplitude sampling."""
        gain = self.gain_V_per_keV.value
        spread = self.spread_std_V.value
        polarity = self.polarity.value
        if gain is not None and gain <= 0.0:
            raise ValueError("gain_V_per_keV must be positive")
        if spread is not None and spread < 0.0:
            raise ValueError("spread_std_V must be non-negative")
        if polarity is not None and polarity not in {-1, 1}:
            raise ValueError("polarity must be -1 or 1")
        return self


class PulseShapeConfig(ConfigModel):
    """Time constants for the future peak-normalized double exponential."""

    tau_r_s: ParameterValue[float]
    tau_d_s: ParameterValue[float]

    @model_validator(mode="after")
    def validate_time_constants(self) -> PulseShapeConfig:
        """Enforce tau_d > tau_r > 0 when both constants are known."""
        tau_r = self.tau_r_s.value
        tau_d = self.tau_d_s.value
        if tau_r is not None and tau_r <= 0.0:
            raise ValueError("tau_r_s must be positive")
        if tau_d is not None and tau_d <= 0.0:
            raise ValueError("tau_d_s must be positive")
        if tau_r is not None and tau_d is not None and tau_d <= tau_r:
            raise ValueError("tau_d_s must be greater than tau_r_s")
        return self


class BaselineConfig(ConfigModel):
    """Placeholder baseline configuration."""

    enabled: bool = True
    offset_V: ParameterValue[float]


class NoiseConfig(ConfigModel):
    """Placeholder noise configuration."""

    enabled: bool = True
    white_noise_rms_V: ParameterValue[float]
    low_frequency_drift_enabled: bool = False

    @model_validator(mode="after")
    def validate_noise(self) -> NoiseConfig:
        """Reject negative RMS values."""
        rms = self.white_noise_rms_V.value
        if rms is not None and rms < 0.0:
            raise ValueError("white_noise_rms_V must be non-negative")
        return self


class ADCConfig(ConfigModel):
    """Placeholder analog-to-digital converter configuration."""

    enabled: bool = True
    bits: ParameterValue[int]
    input_min_V: ParameterValue[float]
    input_max_V: ParameterValue[float]
    offset_V: ParameterValue[float]

    @model_validator(mode="after")
    def validate_adc(self) -> ADCConfig:
        """Validate bit depth and input range when provided."""
        bits = self.bits.value
        low = self.input_min_V.value
        high = self.input_max_V.value
        if bits is not None and bits <= 0:
            raise ValueError("ADC bits must be positive")
        if low is not None and high is not None and high <= low:
            raise ValueError("ADC input_max_V must be greater than input_min_V")
        return self


class TriggerConfig(ConfigModel):
    """Placeholder threshold-trigger configuration."""

    enabled: bool = False
    polarity: ParameterValue[int]
    threshold_V: ParameterValue[float]
    hysteresis_V: ParameterValue[float]
    min_hold_s: ParameterValue[float]

    @model_validator(mode="after")
    def validate_trigger(self) -> TriggerConfig:
        """Validate trigger polarity and non-negative timing fields."""
        polarity = self.polarity.value
        hysteresis = self.hysteresis_V.value
        min_hold = self.min_hold_s.value
        if polarity is not None and polarity not in {-1, 1}:
            raise ValueError("trigger polarity must be -1 or 1")
        if hysteresis is not None and hysteresis < 0.0:
            raise ValueError("hysteresis_V must be non-negative")
        if min_hold is not None and min_hold < 0.0:
            raise ValueError("min_hold_s must be non-negative")
        return self


class DeadTimeMode(StrEnum):
    """Supported future dead-time modes."""

    NONE = "none"
    NONPARALYZABLE = "nonparalyzable"
    PARALYZABLE = "paralyzable"


class DeadTimeConfig(ConfigModel):
    """Placeholder dead-time configuration; no filtering is implemented."""

    mode: DeadTimeMode = DeadTimeMode.NONE
    duration_s: ParameterValue[float]

    @model_validator(mode="after")
    def validate_duration(self) -> DeadTimeConfig:
        """Require non-negative dead time and zero duration for mode none."""
        duration = self.duration_s.value
        if duration is not None and duration < 0.0:
            raise ValueError("dead-time duration_s must be non-negative")
        if self.mode is DeadTimeMode.NONE and duration not in {None, 0.0}:
            raise ValueError("dead-time mode none requires duration_s of zero or null")
        return self


class He3SimConfig(ConfigModel):
    """Top-level Phase 0 configuration contract."""

    schema_version: str = "1"
    metadata: RunMetadataConfig
    simulation: SimulationDomainConfig
    observation: ObservationWindowConfig
    spectrum: EnergySpectrumConfig
    amplitude: AmplitudeCalibrationConfig
    pulse_shape: PulseShapeConfig
    baseline: BaselineConfig
    noise: NoiseConfig
    adc: ADCConfig
    trigger: TriggerConfig
    dead_time: DeadTimeConfig


def load_config(path: str | Path) -> He3SimConfig:
    """Load and validate a YAML configuration file."""
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as stream:
        raw: Any = yaml.safe_load(stream)
    if not isinstance(raw, dict):
        raise ValueError("configuration root must be a YAML mapping")
    return He3SimConfig.model_validate(raw)


def canonical_config_json(config: He3SimConfig) -> str:
    """Return a path-independent, key-order-independent JSON representation."""
    payload = config.model_dump(mode="json", exclude_none=False)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def config_hash(config: He3SimConfig) -> str:
    """Return the SHA-256 digest of the canonical configuration."""
    canonical = canonical_config_json(config).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
