"""Bounded Phase 2 orchestration from truth events to continuous waveform blocks."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel

from he3sim.config import He3SimConfig, ParameterStatus, ParameterValue, WaveformRenderer
from he3sim.physics.arrivals import ArrivalAlgorithm
from he3sim.physics.events import (
    DEFAULT_MAX_EXPECTED_EVENTS,
    TrueEventSimulation,
    simulate_true_events,
)
from he3sim.random import RandomContext
from he3sim.synthesis.baseline import constant_baseline
from he3sim.synthesis.digitizer import clip_analog, quantize_adc
from he3sim.synthesis.noise import AR1DriftGenerator, gaussian_white_noise
from he3sim.synthesis.renderers import (
    RecursiveFixedTauRenderer,
    RecursiveFixedTauState,
    event_first_sample_indices,
    render_direct_sparse_block,
    resolve_renderer_backend,
    waveform_sample_count,
)
from he3sim.types import WaveformBlock

DEFAULT_MAX_WAVEFORM_SAMPLES = 10_000_000


@dataclass(frozen=True, slots=True)
class WaveformSimulation:
    """Prepared truth events and bounded waveform layout metadata."""

    true_events: TrueEventSimulation
    sample_rate_hz: float
    sample_count: int
    block_size: int
    renderer: WaveformRenderer
    parameter_status: ParameterStatus


def _required_value(parameter: ParameterValue[float] | ParameterValue[int], name: str) -> float:
    """Return a required Phase 2 value or fail without inventing a calibration."""
    if parameter.value is None:
        raise ValueError(f"{name} requires an explicit value for waveform simulation")
    return float(parameter.value)


def _section_statuses(model: BaseModel) -> list[ParameterStatus]:
    """Collect evidence states from one flat configuration section."""
    statuses: list[ParameterStatus] = []
    for field_name in type(model).model_fields:
        value = getattr(model, field_name)
        if isinstance(value, ParameterValue):
            statuses.append(value.status)
    return statuses


def waveform_parameter_status(config: He3SimConfig) -> ParameterStatus:
    """Return the least-validated status among parameters used through Phase 2."""
    statuses = [
        *_section_statuses(config.metadata),
        *_section_statuses(config.simulation),
        *_section_statuses(config.observation),
        *_section_statuses(config.spectrum),
        *_section_statuses(config.amplitude),
        *_section_statuses(config.pulse_shape),
        *_section_statuses(config.waveform),
    ]
    if config.baseline.enabled:
        statuses.extend(_section_statuses(config.baseline))
    if config.noise.enabled:
        statuses.extend(_section_statuses(config.noise))
    if config.adc.enabled:
        statuses.extend(_section_statuses(config.adc))
    if ParameterStatus.SYNTHETIC_DEMO in statuses:
        return ParameterStatus.SYNTHETIC_DEMO
    if ParameterStatus.PROVISIONAL in statuses:
        return ParameterStatus.PROVISIONAL
    return ParameterStatus.VALIDATED


def prepare_waveform_simulation(
    config: He3SimConfig,
    algorithm: ArrivalAlgorithm = ArrivalAlgorithm.POISSON_UNIFORM,
    max_expected_events: int = DEFAULT_MAX_EXPECTED_EVENTS,
    max_waveform_samples: int = DEFAULT_MAX_WAVEFORM_SAMPLES,
    renderer_override: WaveformRenderer | None = None,
) -> WaveformSimulation:
    """Generate truth events and map each event to a bounded continuous sample grid."""
    if max_waveform_samples <= 0:
        raise ValueError("max_waveform_samples must be positive")
    if not config.waveform.save_analog and not config.adc.enabled:
        raise ValueError("waveform simulation requires analog or ADC output to be enabled")
    sample_rate_hz = _required_value(config.simulation.sample_rate_hz, "sample_rate_hz")
    block_size = int(_required_value(config.waveform.max_samples_per_block, "block size"))
    true_events = simulate_true_events(config, algorithm, max_expected_events)
    sample_count = waveform_sample_count(true_events.duration_s, sample_rate_hz)
    if sample_count > max_waveform_samples:
        raise ValueError(
            f"waveform sample count {sample_count} exceeds the explicit limit "
            f"{max_waveform_samples}; shorten the horizon or raise the limit"
        )

    events = true_events.events.copy()
    first_indices = event_first_sample_indices(events["t_s"], sample_rate_hz)
    if np.any(first_indices >= sample_count):
        raise RuntimeError("truth event lies outside the allocated waveform grid")
    events["sample_index"] = first_indices
    events["block_id"] = first_indices // block_size
    mapped_truth = TrueEventSimulation(
        events=events,
        duration_s=true_events.duration_s,
        true_rate_cps=true_events.true_rate_cps,
        seed=true_events.seed,
        parameter_status=true_events.parameter_status,
        arrival_algorithm=true_events.arrival_algorithm,
    )
    requested = renderer_override or config.waveform.renderer
    renderer = resolve_renderer_backend(events, requested)
    return WaveformSimulation(
        true_events=mapped_truth,
        sample_rate_hz=sample_rate_hz,
        sample_count=sample_count,
        block_size=block_size,
        renderer=renderer,
        parameter_status=waveform_parameter_status(config),
    )


def iter_waveform_blocks(
    simulation: WaveformSimulation,
    config: He3SimConfig,
) -> Iterator[WaveformBlock]:
    """Yield ordered waveform blocks while retaining pulse and drift state."""
    events = simulation.true_events.events
    tau_r_s = _required_value(config.pulse_shape.tau_r_s, "tau_r_s")
    tau_d_s = _required_value(config.pulse_shape.tau_d_s, "tau_d_s")
    recursive_renderer: RecursiveFixedTauRenderer | None = None
    recursive_state: RecursiveFixedTauState | None = None
    if simulation.renderer is WaveformRenderer.RECURSIVE_FIXED_TAU:
        recursive_renderer = RecursiveFixedTauRenderer.from_events(
            events,
            simulation.sample_rate_hz,
            tau_r_s,
            tau_d_s,
        )

    child_rngs = RandomContext(simulation.true_events.seed).spawn(6)
    white_rng = child_rngs[4]
    drift_rng = child_rngs[5]
    drift_generator: AR1DriftGenerator | None = None
    if config.noise.enabled and config.noise.low_frequency_drift_enabled:
        drift_generator = AR1DriftGenerator(
            rms_V=_required_value(
                config.noise.low_frequency_drift_rms_V,
                "low_frequency_drift_rms_V",
            ),
            correlation_s=_required_value(
                config.noise.low_frequency_drift_correlation_s,
                "low_frequency_drift_correlation_s",
            ),
            sample_rate_hz=simulation.sample_rate_hz,
        )

    baseline_V = (
        _required_value(config.baseline.offset_V, "baseline offset")
        if config.baseline.enabled
        else 0.0
    )
    white_rms_V = (
        _required_value(config.noise.white_noise_rms_V, "white_noise_rms_V")
        if config.noise.enabled
        else 0.0
    )
    analog_min_V = _required_value(config.waveform.analog_clip_min_V, "analog clip minimum")
    analog_max_V = _required_value(config.waveform.analog_clip_max_V, "analog clip maximum")
    first_indices = event_first_sample_indices(events["t_s"], simulation.sample_rate_hz)
    injected_total = 0

    for block_id, sample_start in enumerate(
        range(0, simulation.sample_count, simulation.block_size)
    ):
        sample_count = min(simulation.block_size, simulation.sample_count - sample_start)
        sample_stop = sample_start + sample_count
        if recursive_renderer is not None:
            event_start = int(np.searchsorted(first_indices, sample_start, side="left"))
            event_stop = int(np.searchsorted(first_indices, sample_stop, side="left"))
            pulse_samples_V, recursive_state, injected_count = recursive_renderer.render_block(
                events[event_start:event_stop],
                sample_start,
                sample_count,
                recursive_state,
            )
        else:
            pulse_samples_V = render_direct_sparse_block(
                events,
                sample_start,
                sample_count,
                simulation.sample_rate_hz,
            )
            injected_count = int(
                np.count_nonzero((first_indices >= sample_start) & (first_indices < sample_stop))
            )
        injected_total += injected_count

        analog_samples_V = pulse_samples_V + constant_baseline(sample_count, baseline_V)
        if config.noise.enabled:
            analog_samples_V += gaussian_white_noise(sample_count, white_rms_V, white_rng)
            if drift_generator is not None:
                analog_samples_V += drift_generator.sample(sample_count, drift_rng)
        preclip_analog_samples_V = (
            np.asarray(analog_samples_V, dtype=np.float32) if config.waveform.save_analog else None
        )
        clipped = clip_analog(analog_samples_V, analog_min_V, analog_max_V)

        adc_samples: np.ndarray[tuple[int], np.dtype[np.uint16]] | None = None
        saturation_mask = clipped.saturation_mask
        if config.adc.enabled:
            adc_bits = int(_required_value(config.adc.bits, "ADC bits"))
            digitized = quantize_adc(
                clipped.samples_V,
                adc_bits,
                _required_value(config.adc.input_min_V, "ADC input_min_V"),
                _required_value(config.adc.input_max_V, "ADC input_max_V"),
                _required_value(config.adc.offset_V, "ADC offset_V"),
            )
            adc_samples = digitized.adc_samples
            saturation_mask = saturation_mask | digitized.saturation_mask

        yield WaveformBlock(
            block_id=block_id,
            sample_index_start=sample_start,
            t_start_s=sample_start / simulation.sample_rate_hz,
            sample_rate_hz=simulation.sample_rate_hz,
            preclip_analog_samples_V=preclip_analog_samples_V,
            analog_samples_V=(
                np.asarray(clipped.samples_V, dtype=np.float32)
                if config.waveform.save_analog
                else None
            ),
            adc_samples=adc_samples,
            saturation_mask=np.asarray(saturation_mask, dtype=np.bool_),
        )

    if injected_total != events.size:
        raise RuntimeError(
            f"only {injected_total} of {events.size} truth events were injected "
            "into waveform blocks"
        )
