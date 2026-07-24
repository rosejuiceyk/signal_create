"""Strict configuration for the Phase 6S synthetic residual rehearsal."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, model_validator

from he3sim.config import (
    MAX_TRUE_RATE_CPS,
    MIN_TRUE_RATE_CPS,
    ConfigModel,
    ParameterStatus,
)


class DeviceMode(StrEnum):
    """Explicit execution device selection for the optional ML workflow."""

    CPU = "cpu"
    CUDA = "cuda"
    AUTO = "auto"


class ArtificialInterferenceConfig(ConfigModel):
    """Auditable, non-physical disturbances used in place of measured residuals."""

    parameter_status: ParameterStatus
    source: str = Field(min_length=1)
    white_noise_rms_V: float = Field(ge=0.0)
    colored_noise_rms_V: float = Field(ge=0.0)
    colored_noise_ar: float = Field(ge=0.0, lt=1.0)
    baseline_wander_amplitude_V: float = Field(ge=0.0)
    baseline_cycles_per_patch: float = Field(gt=0.0)
    ringing_amplitude_V: float = Field(ge=0.0)
    ringing_decay_samples: float = Field(gt=0.0)
    ringing_period_samples: float = Field(gt=2.0)
    nonlinear_tail_amplitude_V: float = Field(ge=0.0)
    nonlinear_scale_V: float = Field(gt=0.0)
    max_abs_residual_V: float = Field(gt=0.0)

    @model_validator(mode="after")
    def require_synthetic_status(self) -> ArtificialInterferenceConfig:
        """Prevent artificial disturbances from being presented as calibrated parameters."""
        if self.parameter_status is not ParameterStatus.SYNTHETIC_DEMO:
            raise ValueError("Phase 6S artificial interference must be synthetic_demo")
        return self


class ResidualTCNConfig(ConfigModel):
    """Small FiLM-conditioned TCN architecture and hard output limits."""

    hidden_channels: int = Field(ge=4, le=128)
    kernel_size: int = Field(ge=3, le=15)
    dilations: list[int] = Field(min_length=1, max_length=8)
    input_scale_V: float = Field(gt=0.0)

    @model_validator(mode="after")
    def validate_architecture(self) -> ResidualTCNConfig:
        """Require odd kernels and positive unique dilations."""
        if self.kernel_size % 2 == 0:
            raise ValueError("kernel_size must be odd")
        if any(value <= 0 for value in self.dilations):
            raise ValueError("dilations must be positive")
        if len(set(self.dilations)) != len(self.dilations):
            raise ValueError("dilations must be unique")
        return self


class ResidualTrainingConfig(ConfigModel):
    """Deterministic bounded training and loss settings."""

    seed: int = Field(ge=0)
    device: DeviceMode
    epochs: int = Field(ge=1, le=500)
    batch_size: int = Field(ge=1, le=256)
    learning_rate: float = Field(gt=0.0, le=0.1)
    train_runs_per_rate: int = Field(ge=1, le=256)
    validation_runs_per_rate: int = Field(ge=1, le=256)
    test_runs_per_rate: int = Field(ge=1, le=256)
    huber_weight: float = Field(ge=0.0)
    spectral_weight: float = Field(ge=0.0)
    baseline_weight: float = Field(ge=0.0)
    event_guard_weight: float = Field(ge=0.0)
    residual_energy_weight: float = Field(ge=0.0)

    @model_validator(mode="after")
    def require_supervised_objective(self) -> ResidualTrainingConfig:
        """Require at least one target-matching loss term."""
        if self.huber_weight + self.spectral_weight + self.baseline_weight <= 0.0:
            raise ValueError("at least one supervised loss weight must be positive")
        return self


class SyntheticResidualRehearsalConfig(ConfigModel):
    """Complete Phase 6S contract without any measured-data claim."""

    schema_version: str = "1"
    model_status: str
    physical_config_path: Path
    true_rates_cps: list[float] = Field(min_length=2, max_length=13)
    sample_rate_hz: float = Field(ge=100.0e6, le=250.0e6)
    patch_samples: int = Field(ge=128, le=16384)
    event_guard_samples: int = Field(ge=0, le=64)
    interference: ArtificialInterferenceConfig
    model: ResidualTCNConfig
    training: ResidualTrainingConfig

    @model_validator(mode="after")
    def validate_rehearsal_scope(self) -> SyntheticResidualRehearsalConfig:
        """Keep the rehearsal synthetic, bounded, and inside the supported rate domain."""
        if self.model_status != "synthetic_scaffold":
            raise ValueError("model_status must be synthetic_scaffold")
        if any(not MIN_TRUE_RATE_CPS <= rate <= MAX_TRUE_RATE_CPS for rate in self.true_rates_cps):
            raise ValueError("true_rates_cps must remain within the physical simulator domain")
        if len(set(self.true_rates_cps)) != len(self.true_rates_cps):
            raise ValueError("true_rates_cps must be unique")
        if self.event_guard_samples * 2 + 1 >= self.patch_samples:
            raise ValueError("event guard cannot cover the entire patch")
        total_runs = len(self.true_rates_cps) * (
            self.training.train_runs_per_rate
            + self.training.validation_runs_per_rate
            + self.training.test_runs_per_rate
        )
        if total_runs > 2048:
            raise ValueError("total synthetic run count exceeds the Phase 6S safety limit")
        return self


def load_synthetic_residual_config(path: str | Path) -> SyntheticResidualRehearsalConfig:
    """Load a strict YAML and resolve its physical config relative to that YAML."""
    config_path = Path(path)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("synthetic residual configuration must contain a YAML mapping")
    config = SyntheticResidualRehearsalConfig.model_validate(payload)
    physical_path = config.physical_config_path
    if not physical_path.is_absolute():
        physical_path = (config_path.parent / physical_path).resolve()
    return config.model_copy(update={"physical_config_path": physical_path})


def synthetic_residual_config_payload(
    config: SyntheticResidualRehearsalConfig,
) -> dict[str, Any]:
    """Return a portable payload keyed by physical-config content, not local path."""
    payload = config.model_dump(mode="json")
    physical_path = config.physical_config_path.resolve()
    payload.pop("physical_config_path", None)
    payload["physical_config_sha256"] = hashlib.sha256(physical_path.read_bytes()).hexdigest()
    return payload


def synthetic_residual_config_hash(config: SyntheticResidualRehearsalConfig) -> str:
    """Hash the normalized portable rehearsal contract for checkpoints and reports."""
    payload = synthetic_residual_config_payload(config)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
