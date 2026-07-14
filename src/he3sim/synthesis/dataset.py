"""Phase 3 multi-scale dataset planning with separate event and render horizons."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel

from he3sim.config import He3SimConfig, ParameterStatus, ParameterValue, WaveformRenderer
from he3sim.physics.arrivals import ArrivalAlgorithm
from he3sim.physics.events import (
    DEFAULT_MAX_EXPECTED_EVENTS,
    TrueEventSimulation,
    resolve_duration_s,
)
from he3sim.synthesis.streaming import DEFAULT_MAX_WAVEFORM_SAMPLES, WaveformSimulation
from he3sim.types import TRUE_EVENT_DTYPE


@dataclass(frozen=True, slots=True)
class DatasetSimulation:
    """Truth horizon plus a bounded continuously rendered prefix."""

    true_events: TrueEventSimulation
    waveform: WaveformSimulation
    event_horizon_s: float
    continuous_duration_s: float
    max_windows: int
    max_events: int
    parameter_status: ParameterStatus


def _required(parameter: ParameterValue[float] | ParameterValue[int], name: str) -> float:
    """Return a required Phase 3 value without inventing calibration."""
    if parameter.value is None:
        raise ValueError(f"{name} requires an explicit value for dataset generation")
    return float(parameter.value)


def _statuses(model: BaseModel) -> list[ParameterStatus]:
    statuses: list[ParameterStatus] = []
    for name in type(model).model_fields:
        value = getattr(model, name)
        if isinstance(value, ParameterValue):
            statuses.append(value.status)
    return statuses


def dataset_parameter_status(config: He3SimConfig) -> ParameterStatus:
    """Return the least-validated status among every Phase 3 input parameter."""
    statuses: list[ParameterStatus] = []
    for section in (
        config.metadata,
        config.simulation,
        config.observation,
        config.spectrum,
        config.amplitude,
        config.pulse_shape,
        config.waveform,
        config.baseline,
        config.noise,
        config.adc,
        config.trigger,
        config.dead_time,
        config.dataset,
    ):
        statuses.extend(_statuses(section))
    if ParameterStatus.SYNTHETIC_DEMO in statuses:
        return ParameterStatus.SYNTHETIC_DEMO
    if ParameterStatus.PROVISIONAL in statuses:
        return ParameterStatus.PROVISIONAL
    return ParameterStatus.VALIDATED


def prepare_dataset_simulation(
    config: He3SimConfig,
    algorithm: ArrivalAlgorithm = ArrivalAlgorithm.POISSON_UNIFORM,
    max_expected_events: int = DEFAULT_MAX_EXPECTED_EVENTS,
    max_waveform_samples: int = DEFAULT_MAX_WAVEFORM_SAMPLES,
    renderer_override: WaveformRenderer | None = None,
) -> DatasetSimulation:
    """Generate truth and map only the explicitly bounded continuous prefix."""
    if not config.trigger.enabled:
        raise ValueError("Phase 3 dataset generation requires trigger.enabled=true")
    if not config.waveform.save_analog:
        raise ValueError("Phase 3 voltage triggering currently requires save_analog=true")
    if not config.adc.enabled:
        raise ValueError("Phase 3 event windows require adc.enabled=true")
    if max_waveform_samples <= 0:
        raise ValueError("max_waveform_samples must be positive")
    sample_rate_hz = _required(config.simulation.sample_rate_hz, "sample_rate_hz")
    block_size = int(_required(config.waveform.max_samples_per_block, "block size"))
    if algorithm is not ArrivalAlgorithm.POISSON_UNIFORM:
        raise ValueError("Phase 3 streaming datasets currently require poisson_uniform")
    event_horizon_s = resolve_duration_s(config)
    true_rate_cps = _required(config.simulation.true_rate_cps, "true_rate_cps")
    if true_rate_cps * event_horizon_s > max_expected_events:
        raise ValueError("expected streaming event count exceeds the explicit limit")
    requested_continuous_s = _required(
        config.dataset.continuous_duration_s,
        "continuous_duration_s",
    )
    continuous_duration_s = min(event_horizon_s, requested_continuous_s)
    sample_count = math.ceil(continuous_duration_s * sample_rate_hz) + 1
    if sample_count > max_waveform_samples:
        raise ValueError(
            f"continuous sample count {sample_count} exceeds the explicit limit "
            f"{max_waveform_samples}; shorten dataset.continuous_duration_s"
        )

    if config.metadata.seed.value is None:
        raise ValueError("seed requires an explicit value")
    empty_events = np.empty(0, dtype=TRUE_EVENT_DTYPE)
    rendered_truth = TrueEventSimulation(
        events=empty_events,
        duration_s=continuous_duration_s,
        true_rate_cps=true_rate_cps,
        seed=config.metadata.seed.value,
        parameter_status=dataset_parameter_status(config),
        arrival_algorithm=algorithm,
    )
    requested_renderer = renderer_override or config.waveform.renderer
    if requested_renderer is WaveformRenderer.DIRECT_SPARSE:
        raise ValueError("Phase 3 streaming requires recursive_fixed_tau or auto")
    waveform = WaveformSimulation(
        true_events=rendered_truth,
        sample_rate_hz=sample_rate_hz,
        sample_count=sample_count,
        block_size=block_size,
        renderer=WaveformRenderer.RECURSIVE_FIXED_TAU,
        parameter_status=dataset_parameter_status(config),
    )
    return DatasetSimulation(
        true_events=rendered_truth,
        waveform=waveform,
        event_horizon_s=event_horizon_s,
        continuous_duration_s=continuous_duration_s,
        max_windows=int(_required(config.dataset.max_windows, "max_windows")),
        max_events=max_expected_events,
        parameter_status=dataset_parameter_status(config),
    )
