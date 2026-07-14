"""Validated configuration models and deterministic configuration hashing."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Generic, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

T = TypeVar("T")

MIN_TRUE_RATE_CPS = 10.0
MAX_TRUE_RATE_CPS = 1.0e7


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
    seed: ParameterValue[StrictInt]

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
        if rate is not None and not MIN_TRUE_RATE_CPS <= rate <= MAX_TRUE_RATE_CPS:
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
    min_duration_s: ParameterValue[float] | None = None
    max_duration_s: ParameterValue[float] | None = None

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
        minimum = self.min_duration_s.value if self.min_duration_s is not None else None
        maximum = self.max_duration_s.value if self.max_duration_s is not None else None
        if minimum is not None and minimum <= 0.0:
            raise ValueError("min_duration_s must be positive")
        if maximum is not None and maximum <= 0.0:
            raise ValueError("max_duration_s must be positive")
        if minimum is not None and maximum is not None and maximum < minimum:
            raise ValueError("max_duration_s must be greater than or equal to min_duration_s")
        if self.mode is ObservationMode.FIXED_DURATION and self.duration_s is not None:
            duration = self.duration_s.value
            if duration is not None and minimum is not None and duration < minimum:
                raise ValueError("duration_s cannot be shorter than min_duration_s")
            if duration is not None and maximum is not None and duration > maximum:
                raise ValueError("duration_s cannot exceed max_duration_s")
        return self


class EnergySpectrumConfig(ConfigModel):
    """Parameters for the Phase 1 He-3 deposited-energy mixture model."""

    provider: str = "parametric_he3"
    full_energy_keV: ParameterValue[float]
    full_energy_sigma_keV: ParameterValue[float]
    full_energy_fraction: ParameterValue[float]
    proton_wall_fraction: ParameterValue[float]
    proton_wall_min_keV: ParameterValue[float]
    proton_wall_max_keV: ParameterValue[float]
    proton_wall_alpha: ParameterValue[float]
    proton_wall_beta: ParameterValue[float]
    triton_wall_fraction: ParameterValue[float]
    triton_wall_min_keV: ParameterValue[float]
    triton_wall_max_keV: ParameterValue[float]
    triton_wall_alpha: ParameterValue[float]
    triton_wall_beta: ParameterValue[float]
    double_wall_fraction: ParameterValue[float]
    double_wall_min_keV: ParameterValue[float]
    double_wall_max_keV: ParameterValue[float]
    double_wall_alpha: ParameterValue[float]
    double_wall_beta: ParameterValue[float]

    @model_validator(mode="after")
    def validate_spectrum_parameters(self) -> EnergySpectrumConfig:
        """Validate mixture weights, component domains, and shape parameters."""
        weights = [
            self.full_energy_fraction.value,
            self.proton_wall_fraction.value,
            self.triton_wall_fraction.value,
            self.double_wall_fraction.value,
        ]
        known_weights = [value for value in weights if value is not None]
        if any(value < 0.0 for value in known_weights):
            raise ValueError("spectrum mixture weights must be non-negative")
        if len(known_weights) == len(weights) and not math.isclose(
            sum(known_weights), 1.0, rel_tol=0.0, abs_tol=1.0e-9
        ):
            raise ValueError("spectrum mixture weights must sum to one")

        full_energy = self.full_energy_keV.value
        sigma = self.full_energy_sigma_keV.value
        if full_energy is not None and full_energy <= 0.0:
            raise ValueError("full_energy_keV must be positive")
        if sigma is not None and sigma < 0.0:
            raise ValueError("full_energy_sigma_keV must be non-negative")

        components = {
            "proton_wall": (
                self.proton_wall_min_keV.value,
                self.proton_wall_max_keV.value,
                self.proton_wall_alpha.value,
                self.proton_wall_beta.value,
            ),
            "triton_wall": (
                self.triton_wall_min_keV.value,
                self.triton_wall_max_keV.value,
                self.triton_wall_alpha.value,
                self.triton_wall_beta.value,
            ),
            "double_wall": (
                self.double_wall_min_keV.value,
                self.double_wall_max_keV.value,
                self.double_wall_alpha.value,
                self.double_wall_beta.value,
            ),
        }
        for name, (minimum, maximum, alpha, beta) in components.items():
            if minimum is not None and minimum < 0.0:
                raise ValueError(f"{name} minimum energy must be non-negative")
            if minimum is not None and maximum is not None and maximum <= minimum:
                raise ValueError(f"{name} maximum energy must exceed its minimum")
            if maximum is not None and full_energy is not None and maximum > full_energy:
                raise ValueError(f"{name} maximum energy cannot exceed full_energy_keV")
            if alpha is not None and alpha <= 0.0:
                raise ValueError(f"{name} alpha must be positive")
            if beta is not None and beta <= 0.0:
                raise ValueError(f"{name} beta must be positive")
        return self


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
    """Time constants for the peak-normalized double exponential."""

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


class WaveformRenderer(StrEnum):
    """Available Phase 2 continuous-waveform rendering backends."""

    DIRECT_SPARSE = "direct_sparse"
    RECURSIVE_FIXED_TAU = "recursive_fixed_tau"
    AUTO = "auto"


class WaveformSynthesisConfig(ConfigModel):
    """Bounded block rendering and analog clipping configuration."""

    renderer: WaveformRenderer = WaveformRenderer.AUTO
    max_samples_per_block: ParameterValue[StrictInt]
    save_analog: bool = True
    analog_clip_min_V: ParameterValue[float]
    analog_clip_max_V: ParameterValue[float]

    @model_validator(mode="after")
    def validate_waveform_fields(self) -> WaveformSynthesisConfig:
        """Require a positive block bound and an ordered analog range."""
        block_size = self.max_samples_per_block.value
        low = self.analog_clip_min_V.value
        high = self.analog_clip_max_V.value
        if block_size is not None and block_size <= 0:
            raise ValueError("max_samples_per_block must be positive")
        if low is not None and high is not None and high <= low:
            raise ValueError("analog_clip_max_V must be greater than analog_clip_min_V")
        return self


class BaselineConfig(ConfigModel):
    """Constant baseline configuration."""

    enabled: bool = True
    offset_V: ParameterValue[float]


class NoiseConfig(ConfigModel):
    """White-noise and optional stationary AR(1) drift configuration."""

    enabled: bool = True
    white_noise_rms_V: ParameterValue[float]
    low_frequency_drift_enabled: bool = False
    low_frequency_drift_rms_V: ParameterValue[float]
    low_frequency_drift_correlation_s: ParameterValue[float]

    @model_validator(mode="after")
    def validate_noise(self) -> NoiseConfig:
        """Reject invalid RMS values and require resolvable drift parameters."""
        white_rms = self.white_noise_rms_V.value
        drift_rms = self.low_frequency_drift_rms_V.value
        correlation_s = self.low_frequency_drift_correlation_s.value
        if white_rms is not None and white_rms < 0.0:
            raise ValueError("white_noise_rms_V must be non-negative")
        if drift_rms is not None and drift_rms < 0.0:
            raise ValueError("low_frequency_drift_rms_V must be non-negative")
        if correlation_s is not None and correlation_s <= 0.0:
            raise ValueError("low_frequency_drift_correlation_s must be positive")
        if self.low_frequency_drift_enabled and (drift_rms is None or correlation_s is None):
            raise ValueError("enabled low-frequency drift requires RMS and correlation time")
        return self


class ADCConfig(ConfigModel):
    """Uniform ADC quantization configuration."""

    enabled: bool = True
    bits: ParameterValue[StrictInt]
    input_min_V: ParameterValue[float]
    input_max_V: ParameterValue[float]
    offset_V: ParameterValue[float]

    @model_validator(mode="after")
    def validate_adc(self) -> ADCConfig:
        """Validate bit depth and input range when provided."""
        bits = self.bits.value
        low = self.input_min_V.value
        high = self.input_max_V.value
        if bits is not None and not 1 <= bits <= 16:
            raise ValueError("ADC bits must be within [1, 16]")
        if low is not None and high is not None and high <= low:
            raise ValueError("ADC input_max_V must be greater than input_min_V")
        return self


class TriggerConfig(ConfigModel):
    """Threshold trigger and fixed event-window configuration."""

    enabled: bool = False
    polarity: ParameterValue[int]
    threshold_V: ParameterValue[float]
    hysteresis_V: ParameterValue[float]
    min_hold_s: ParameterValue[float]
    pre_trigger_s: ParameterValue[float]
    post_trigger_s: ParameterValue[float]

    @model_validator(mode="after")
    def validate_trigger(self) -> TriggerConfig:
        """Validate trigger polarity and non-negative timing fields."""
        polarity = self.polarity.value
        hysteresis = self.hysteresis_V.value
        min_hold = self.min_hold_s.value
        pre_trigger = self.pre_trigger_s.value
        post_trigger = self.post_trigger_s.value
        if polarity is not None and polarity not in {-1, 1}:
            raise ValueError("trigger polarity must be -1 or 1")
        if hysteresis is not None and hysteresis < 0.0:
            raise ValueError("hysteresis_V must be non-negative")
        if min_hold is not None and min_hold < 0.0:
            raise ValueError("min_hold_s must be non-negative")
        if pre_trigger is not None and pre_trigger < 0.0:
            raise ValueError("pre_trigger_s must be non-negative")
        if post_trigger is not None and post_trigger <= 0.0:
            raise ValueError("post_trigger_s must be positive")
        if self.enabled:
            values = {
                "polarity": polarity,
                "threshold_V": self.threshold_V.value,
                "hysteresis_V": hysteresis,
                "min_hold_s": min_hold,
                "pre_trigger_s": pre_trigger,
                "post_trigger_s": post_trigger,
            }
            missing = [name for name, value in values.items() if value is None]
            if missing:
                raise ValueError(f"enabled trigger requires values for {', '.join(missing)}")
            assert polarity is not None
            assert self.threshold_V.value is not None
            threshold_magnitude = polarity * self.threshold_V.value
            if threshold_magnitude <= 0.0:
                raise ValueError("trigger threshold_V sign must match trigger polarity")
            assert hysteresis is not None
            if hysteresis >= threshold_magnitude:
                raise ValueError("trigger hysteresis_V must be below threshold magnitude")
        return self


class DeadTimeMode(StrEnum):
    """Supported future dead-time modes."""

    NONE = "none"
    NONPARALYZABLE = "nonparalyzable"
    PARALYZABLE = "paralyzable"


class DeadTimeConfig(ConfigModel):
    """Observation-layer dead-time configuration."""

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
        if self.mode is not DeadTimeMode.NONE and (duration is None or duration <= 0.0):
            raise ValueError("enabled dead-time mode requires a positive duration_s")
        return self


class DatasetConfig(ConfigModel):
    """Phase 3 bounded continuous-region and HDF5 storage controls."""

    continuous_duration_s: ParameterValue[float]
    max_windows: ParameterValue[StrictInt]
    compression: str = "gzip"
    compression_level: StrictInt = Field(default=4, ge=0, le=9)

    @model_validator(mode="after")
    def validate_dataset(self) -> DatasetConfig:
        """Reject unbounded or unsupported dataset controls."""
        duration = self.continuous_duration_s.value
        max_windows = self.max_windows.value
        if duration is not None and duration <= 0.0:
            raise ValueError("continuous_duration_s must be positive")
        if max_windows is not None and max_windows <= 0:
            raise ValueError("max_windows must be positive")
        if self.compression not in {"gzip", "lzf"}:
            raise ValueError("dataset compression must be gzip or lzf")
        if self.compression == "lzf" and self.compression_level != 0:
            raise ValueError("lzf compression requires compression_level 0")
        return self


class He3SimConfig(ConfigModel):
    """Top-level configuration contract used through Phase 3."""

    schema_version: str = "1"
    metadata: RunMetadataConfig
    simulation: SimulationDomainConfig
    observation: ObservationWindowConfig
    spectrum: EnergySpectrumConfig
    amplitude: AmplitudeCalibrationConfig
    pulse_shape: PulseShapeConfig
    waveform: WaveformSynthesisConfig
    baseline: BaselineConfig
    noise: NoiseConfig
    adc: ADCConfig
    trigger: TriggerConfig
    dead_time: DeadTimeConfig
    dataset: DatasetConfig


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
