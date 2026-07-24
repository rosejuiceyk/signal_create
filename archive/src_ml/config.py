"""Strict YAML configuration for the experimental Phase 5 event model."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import Field, model_validator

from he3sim.config import MAX_TRUE_RATE_CPS, MIN_TRUE_RATE_CPS, ConfigModel

STANDARD_RATES_CPS = (
    10.0,
    30.0,
    100.0,
    300.0,
    1.0e3,
    3.0e3,
    1.0e4,
    3.0e4,
    1.0e5,
    3.0e5,
    1.0e6,
    3.0e6,
    1.0e7,
)
INTERPOLATION_RATES_CPS = tuple(
    float((left * right) ** 0.5)
    for left, right in zip(STANDARD_RATES_CPS[:-1], STANDARD_RATES_CPS[1:], strict=True)
)


class MLDevice(StrEnum):
    """Explicit training or inference device selection."""

    AUTO = "auto"
    CPU = "cpu"
    CUDA = "cuda"


class EventModelArchitectureConfig(ConfigModel):
    """Small conditional density-network architecture."""

    hidden_dim: int = Field(default=64, ge=16, le=512)
    hidden_layers: int = Field(default=2, ge=1, le=6)
    interval_mixture_components: int = Field(default=3, ge=2, le=8)
    minimum_scale: float = Field(default=0.02, gt=0.0, le=1.0)


class EventModelTrainingConfig(ConfigModel):
    """Training, synthetic-data, checkpoint, and device controls."""

    base_config_path: Path
    output_directory: Path
    resume_from: Path | None = None
    device: MLDevice = MLDevice.AUTO
    seed: int = Field(default=20260714, ge=0)
    train_windows: int = Field(default=768, ge=8, le=100_000)
    validation_windows: int = Field(default=130, ge=13, le=100_000)
    epochs: int = Field(default=20, ge=1, le=10_000)
    batch_size: int = Field(default=64, ge=1, le=4096)
    learning_rate: float = Field(default=2.0e-3, gt=0.0, le=1.0)
    checkpoint_every: int = Field(default=5, ge=1)
    rate_min_cps: float = Field(default=MIN_TRUE_RATE_CPS, ge=MIN_TRUE_RATE_CPS)
    rate_max_cps: float = Field(default=MAX_TRUE_RATE_CPS, le=MAX_TRUE_RATE_CPS)
    expected_events_min: float = Field(default=8.0, gt=0.0)
    expected_events_max: float = Field(default=64.0, gt=0.0)
    max_events_per_window: int = Field(default=512, ge=1, le=1_000_000)
    architecture: EventModelArchitectureConfig = EventModelArchitectureConfig()

    @model_validator(mode="after")
    def validate_training_range(self) -> EventModelTrainingConfig:
        """Require ordered supported rates and bounded expected counts."""
        if self.rate_max_cps <= self.rate_min_cps:
            raise ValueError("rate_max_cps must be greater than rate_min_cps")
        if self.expected_events_max <= self.expected_events_min:
            raise ValueError("expected_events_max must be greater than expected_events_min")
        if self.expected_events_max > self.max_events_per_window / 2:
            raise ValueError("expected_events_max must leave headroom below max_events_per_window")
        return self


class EventModelEvaluationThresholds(ConfigModel):
    """Research-level statistical matching thresholds, not promotion criteria."""

    maximum_rate_relative_bias: float = Field(default=0.12, gt=0.0, lt=1.0)
    maximum_fano_error: float = Field(default=0.35, gt=0.0)
    maximum_interval_ks: float = Field(default=0.12, gt=0.0, lt=1.0)
    maximum_interval_lag1_abs: float = Field(default=0.12, gt=0.0, lt=1.0)
    maximum_event_type_tv: float = Field(default=0.10, gt=0.0, lt=1.0)
    maximum_energy_quantile_error: float = Field(default=0.12, gt=0.0)
    maximum_amplitude_quantile_error: float = Field(default=0.12, gt=0.0)
    maximum_tau_quantile_relative_error: float = Field(default=0.12, gt=0.0)
    maximum_energy_amplitude_correlation_error: float = Field(default=0.15, gt=0.0)


class EventModelEvaluationConfig(ConfigModel):
    """Checkpoint comparison against the exact physical event generator."""

    base_config_path: Path
    checkpoint_path: Path
    device: MLDevice = MLDevice.AUTO
    seed: int = Field(default=20260715, ge=0)
    replicates_per_rate: int = Field(default=96, ge=8, le=10_000)
    expected_events_per_window: float = Field(default=32.0, gt=0.0)
    max_events_per_window: int = Field(default=512, ge=1, le=1_000_000)
    standard_rates_cps: tuple[float, ...] = STANDARD_RATES_CPS
    interpolation_rates_cps: tuple[float, ...] = INTERPOLATION_RATES_CPS
    thresholds: EventModelEvaluationThresholds = EventModelEvaluationThresholds()

    @model_validator(mode="after")
    def validate_evaluation_rates(self) -> EventModelEvaluationConfig:
        """Reject empty, duplicate, or unsupported evaluation rates."""
        rates = self.standard_rates_cps + self.interpolation_rates_cps
        if not rates:
            raise ValueError("at least one evaluation rate is required")
        if len(set(rates)) != len(rates):
            raise ValueError("evaluation rates must be unique")
        if any(rate < MIN_TRUE_RATE_CPS or rate > MAX_TRUE_RATE_CPS for rate in rates):
            raise ValueError("evaluation rates must remain within [10, 1e7] cps")
        if self.expected_events_per_window > self.max_events_per_window / 2:
            raise ValueError(
                "expected_events_per_window must leave headroom below max_events_per_window"
            )
        return self


MLConfig = TypeVar("MLConfig", EventModelTrainingConfig, EventModelEvaluationConfig)


def _resolve_path(value: Path | None, parent: Path) -> Path | None:
    if value is None or value.is_absolute():
        return value
    return (parent / value).resolve()


def _load_ml_config(path: str | Path, model_type: type[MLConfig]) -> MLConfig:
    config_path = Path(path).resolve()
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError("ML configuration root must be a mapping")
    config = model_type.model_validate(raw)
    parent = config_path.parent
    if isinstance(config, EventModelTrainingConfig):
        return config.model_copy(
            update={
                "base_config_path": _resolve_path(config.base_config_path, parent),
                "output_directory": _resolve_path(config.output_directory, parent),
                "resume_from": _resolve_path(config.resume_from, parent),
            }
        )
    return config.model_copy(
        update={
            "base_config_path": _resolve_path(config.base_config_path, parent),
            "checkpoint_path": _resolve_path(config.checkpoint_path, parent),
        }
    )


def load_event_model_training_config(path: str | Path) -> EventModelTrainingConfig:
    """Load and resolve one strict Phase 5 training YAML file."""
    return _load_ml_config(path, EventModelTrainingConfig)


def load_event_model_evaluation_config(path: str | Path) -> EventModelEvaluationConfig:
    """Load and resolve one strict Phase 5 evaluation YAML file."""
    return _load_ml_config(path, EventModelEvaluationConfig)


def ml_config_hash(config: ConfigModel) -> str:
    """Hash normalized ML configuration without relying on YAML key order."""
    payload: dict[str, Any] = config.model_dump(mode="json")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
