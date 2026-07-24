"""Atomic, compressed Phase 3 HDF5 dataset writer."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import h5py  # type: ignore[import-untyped]
import numpy as np
import numpy.typing as npt

from he3sim import __version__
from he3sim.acquisition.dead_time import apply_dead_time
from he3sim.acquisition.event_matching import match_triggers_to_truth
from he3sim.acquisition.trigger import ThresholdTrigger, TriggerState
from he3sim.analysis.pulse_features import extract_pulse_features
from he3sim.config import (
    He3SimConfig,
    ParameterValue,
    SourceModelKind,
    canonical_config_json,
    config_hash,
)
from he3sim.physics.event_stream import StreamingTrueEventGenerator
from he3sim.random import RandomContext
from he3sim.synthesis.baseline import constant_baseline
from he3sim.synthesis.dataset import DatasetSimulation
from he3sim.synthesis.digitizer import clip_analog, quantize_adc
from he3sim.synthesis.noise import AR1DriftGenerator, gaussian_white_noise
from he3sim.synthesis.renderers import RecursiveFixedTauRenderer, RecursiveFixedTauState
from he3sim.types import (
    EVENT_LINEAGE_DTYPE,
    OBSERVED_EVENT_DTYPE,
    TRIGGER_EVENT_LINK_DTYPE,
    TRUE_EVENT_DTYPE,
    WAVEFORM_BLOCK_INDEX_DTYPE,
    WINDOW_METADATA_DTYPE,
)

DATASET_UNITS = {
    "t_s": "s",
    "trigger_time_s": "s",
    "event_time_offset_s": "s",
    "energy_dep_keV": "keV",
    "amplitude_peak_V": "V",
    "tau_r_s": "s",
    "tau_d_s": "s",
    "analog_samples": "V",
    "adc_samples": "code",
    "peak_V": "V",
    "integral_V_s": "V*s",
    "rise_time_10_90_s": "s",
    "fall_time_90_10_s": "s",
    "sample_rate_hz": "Hz",
}

EVENT_STREAM_TARGET_CHUNK_EVENTS = 16_384
EVENT_STREAM_MAX_CHUNK_EVENTS = 32_768


def _required(parameter: ParameterValue[float] | ParameterValue[int], name: str) -> float:
    if parameter.value is None:
        raise ValueError(f"{name} requires an explicit Phase 3 value")
    return float(parameter.value)


def _compression_kwargs(config: He3SimConfig) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"compression": config.dataset.compression, "shuffle": True}
    if config.dataset.compression == "gzip":
        kwargs["compression_opts"] = config.dataset.compression_level
    return kwargs


def _resolve_output_path(output_path: str | Path) -> Path:
    path = Path(output_path)
    if path.suffix.lower() not in {".h5", ".hdf5"}:
        path = path / "dataset.h5"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _create_metadata(
    handle: h5py.File,
    simulation: DatasetSimulation,
    config: He3SimConfig,
) -> None:
    metadata = handle.create_group("metadata")
    string_dtype = h5py.string_dtype(encoding="utf-8")
    metadata.create_dataset(
        "config_json",
        data=canonical_config_json(config),
        dtype=string_dtype,
    )
    metadata.attrs["config_hash"] = config_hash(config)
    metadata.attrs["code_version"] = __version__
    metadata.attrs["seed"] = simulation.true_events.seed
    metadata.attrs["parameter_status"] = simulation.parameter_status.value
    metadata.attrs["units_json"] = json.dumps(DATASET_UNITS, sort_keys=True)
    metadata.attrs["arrival_algorithm"] = simulation.true_events.arrival_algorithm.value
    metadata.attrs["source_model"] = simulation.true_events.source_model.value
    metadata.attrs["renderer"] = simulation.waveform.renderer.value
    metadata.attrs["true_rate_cps"] = simulation.true_events.true_rate_cps
    metadata.attrs["event_horizon_s"] = simulation.event_horizon_s
    metadata.attrs["continuous_duration_s"] = simulation.continuous_duration_s
    metadata.attrs["sample_rate_hz"] = simulation.waveform.sample_rate_hz
    metadata.attrs["sample_count"] = simulation.waveform.sample_count
    metadata.attrs["block_size"] = simulation.waveform.block_size
    metadata.attrs["dead_time_mode"] = config.dead_time.mode.value
    metadata.attrs["dead_time_duration_s"] = _required(
        config.dead_time.duration_s, "dead-time duration"
    )
    if simulation.true_events.derived_source_metadata is not None:
        metadata.attrs["source_model_derived_json"] = json.dumps(
            simulation.true_events.derived_source_metadata,
            sort_keys=True,
        )


def write_dataset_hdf5(
    output_path: str | Path,
    simulation: DatasetSimulation,
    config: He3SimConfig,
) -> Path:
    """Stream waveform blocks, then persist observation tables and fixed windows."""
    path = _resolve_output_path(output_path)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    waveform = simulation.waveform
    chunk_length = min(waveform.block_size, waveform.sample_count)
    block_count = math.ceil(waveform.sample_count / waveform.block_size)
    compression = _compression_kwargs(config)
    pre_s = _required(config.trigger.pre_trigger_s, "pre_trigger_s")
    post_s = _required(config.trigger.post_trigger_s, "post_trigger_s")
    pre_samples = math.ceil(pre_s * waveform.sample_rate_hz)
    post_samples = math.ceil(post_s * waveform.sample_rate_hz)
    window_length = pre_samples + post_samples + 1
    trigger = ThresholdTrigger(
        waveform.sample_rate_hz,
        int(_required(config.trigger.polarity, "trigger polarity")),
        _required(config.trigger.threshold_V, "trigger threshold"),
        _required(config.trigger.hysteresis_V, "trigger hysteresis"),
        _required(config.trigger.min_hold_s, "trigger hold time"),
    )

    try:
        with h5py.File(temporary_path, "w") as handle:
            _create_metadata(handle, simulation, config)
            events_group = handle.create_group("events")
            true_dataset = events_group.create_dataset(
                "true",
                shape=(0,),
                dtype=TRUE_EVENT_DTYPE,
                maxshape=(None,),
                chunks=True,
                **compression,
            )
            lineage_dataset: h5py.Dataset | None = None
            if simulation.true_events.source_model is SourceModelKind.CORRELATED:
                lineage_dataset = events_group.create_dataset(
                    "lineage",
                    shape=(0,),
                    dtype=EVENT_LINEAGE_DTYPE,
                    maxshape=(None,),
                    chunks=True,
                    **compression,
                )

            blocks = handle.create_group("blocks")
            analog_dataset = blocks.create_dataset(
                "analog_samples",
                shape=(waveform.sample_count,),
                dtype=np.float32,
                chunks=(chunk_length,),
                **compression,
            )
            adc_dataset = blocks.create_dataset(
                "adc_samples",
                shape=(waveform.sample_count,),
                dtype=np.uint16,
                chunks=(chunk_length,),
                **compression,
            )
            saturation_dataset = blocks.create_dataset(
                "saturation_mask",
                shape=(waveform.sample_count,),
                dtype=np.bool_,
                chunks=(chunk_length,),
                **compression,
            )
            index_dataset = blocks.create_dataset(
                "index",
                shape=(block_count,),
                dtype=WAVEFORM_BLOCK_INDEX_DTYPE,
            )
            event_generator = StreamingTrueEventGenerator(
                config,
                max_events=simulation.max_events,
                max_chunk_events=EVENT_STREAM_MAX_CHUNK_EVENTS,
            )
            tau_r_s = _required(config.pulse_shape.tau_r_s, "tau_r_s")
            tau_d_s = _required(config.pulse_shape.tau_d_s, "tau_d_s")
            recursive = RecursiveFixedTauRenderer(
                waveform.sample_rate_hz,
                tau_r_s,
                tau_d_s,
            )
            recursive_state: RecursiveFixedTauState | None = None
            noise_rngs = RandomContext(simulation.true_events.seed).spawn(6)
            white_rng = noise_rngs[4]
            drift_rng = noise_rngs[5]
            drift: AR1DriftGenerator | None = None
            if config.noise.enabled and config.noise.low_frequency_drift_enabled:
                drift = AR1DriftGenerator(
                    _required(config.noise.low_frequency_drift_rms_V, "drift RMS"),
                    _required(
                        config.noise.low_frequency_drift_correlation_s,
                        "drift correlation",
                    ),
                    waveform.sample_rate_hz,
                )
            baseline_V = (
                _required(config.baseline.offset_V, "baseline offset")
                if config.baseline.enabled
                else 0.0
            )
            white_rms_V = (
                _required(config.noise.white_noise_rms_V, "white noise RMS")
                if config.noise.enabled
                else 0.0
            )
            analog_min_V = _required(config.waveform.analog_clip_min_V, "analog clip minimum")
            analog_max_V = _required(config.waveform.analog_clip_max_V, "analog clip maximum")
            adc_bits = int(_required(config.adc.bits, "ADC bits"))
            adc_min_V = _required(config.adc.input_min_V, "ADC input minimum")
            adc_max_V = _required(config.adc.input_max_V, "ADC input maximum")
            adc_offset_V = _required(config.adc.offset_V, "ADC offset")
            trigger_state: TriggerState | None = None
            candidate_chunks: list[npt.NDArray[np.int64]] = []
            rendered_event_chunks: list[npt.NDArray[np.void]] = []
            pending_events = np.empty(0, dtype=TRUE_EVENT_DTYPE)
            event_time_cursor_s = 0.0
            written_blocks = 0
            saturated_samples = 0
            for block_id, start in enumerate(range(0, waveform.sample_count, waveform.block_size)):
                sample_count = min(waveform.block_size, waveform.sample_count - start)
                stop = start + sample_count
                interval_stop_s = min(
                    simulation.continuous_duration_s,
                    stop / waveform.sample_rate_hz,
                )
                generated = np.empty(0, dtype=TRUE_EVENT_DTYPE)
                if interval_stop_s > event_time_cursor_s:
                    generated = event_generator.sample_interval(
                        event_time_cursor_s,
                        interval_stop_s,
                        waveform.sample_rate_hz,
                        waveform.block_size,
                    )
                    event_time_cursor_s = interval_stop_s
                    old_size = true_dataset.shape[0]
                    true_dataset.resize((old_size + generated.size,))
                    true_dataset[old_size:] = generated
                    if lineage_dataset is not None:
                        lineage = event_generator.last_lineage
                        if lineage.size != generated.size:
                            raise RuntimeError("lineage and truth chunks are not aligned")
                        lineage_dataset.resize((old_size + lineage.size,))
                        lineage_dataset[old_size:] = lineage
                    if generated.size:
                        rendered_event_chunks.append(generated)
                available = (
                    np.concatenate((pending_events, generated))
                    if pending_events.size or generated.size
                    else np.empty(0, dtype=TRUE_EVENT_DTYPE)
                )
                current_mask = available["sample_index"] < stop
                block_events = available[current_mask]
                pending_events = available[~current_mask]
                pulse_samples_V, recursive_state, injected_count = recursive.render_block(
                    block_events,
                    start,
                    sample_count,
                    recursive_state,
                )
                analog_values = pulse_samples_V + constant_baseline(sample_count, baseline_V)
                if config.noise.enabled:
                    analog_values += gaussian_white_noise(sample_count, white_rms_V, white_rng)
                    if drift is not None:
                        analog_values += drift.sample(sample_count, drift_rng)
                clipped = clip_analog(analog_values, analog_min_V, analog_max_V)
                digitized = quantize_adc(
                    clipped.samples_V,
                    adc_bits,
                    adc_min_V,
                    adc_max_V,
                    adc_offset_V,
                )
                analog_block = np.asarray(clipped.samples_V, dtype=np.float32)
                adc_block = digitized.adc_samples
                saturation_block = clipped.saturation_mask | digitized.saturation_mask
                analog_dataset[start:stop] = analog_block
                adc_dataset[start:stop] = adc_block
                saturation_dataset[start:stop] = saturation_block
                saturated_samples += int(np.count_nonzero(saturation_block))
                candidates, trigger_state = trigger.process_block(
                    analog_block,
                    start,
                    trigger_state,
                )
                if candidates.size:
                    candidate_chunks.append(candidates)
                index_dataset[written_blocks] = (
                    block_id,
                    start,
                    sample_count,
                    start / waveform.sample_rate_hz,
                    waveform.sample_rate_hz,
                    injected_count,
                )
                written_blocks += 1
            if written_blocks != block_count:
                raise RuntimeError("dataset writer did not receive every waveform block")
            if pending_events.size:
                raise RuntimeError(
                    "renderable truth events remained after the final waveform block"
                )

            remaining_s = simulation.event_horizon_s - event_time_cursor_s
            event_only_chunk_s = (
                EVENT_STREAM_TARGET_CHUNK_EVENTS / simulation.true_events.true_rate_cps
            )
            while remaining_s > 0.0:
                interval_stop_s = min(
                    simulation.event_horizon_s,
                    event_time_cursor_s + event_only_chunk_s,
                )
                generated = event_generator.sample_interval(event_time_cursor_s, interval_stop_s)
                old_size = true_dataset.shape[0]
                true_dataset.resize((old_size + generated.size,))
                true_dataset[old_size:] = generated
                if lineage_dataset is not None:
                    lineage = event_generator.last_lineage
                    if lineage.size != generated.size:
                        raise RuntimeError("lineage and truth chunks are not aligned")
                    lineage_dataset.resize((old_size + lineage.size,))
                    lineage_dataset[old_size:] = lineage
                event_time_cursor_s = interval_stop_s
                remaining_s = simulation.event_horizon_s - event_time_cursor_s

            rendered_events = (
                np.concatenate(rendered_event_chunks)
                if rendered_event_chunks
                else np.empty(0, dtype=TRUE_EVENT_DTYPE)
            )

            candidate_indices = (
                np.concatenate(candidate_chunks)
                if candidate_chunks
                else np.empty(0, dtype=np.int64)
            )
            candidate_times_s = candidate_indices.astype(np.float64) / waveform.sample_rate_hz
            dead_time = apply_dead_time(
                candidate_times_s,
                _required(config.dead_time.duration_s, "dead-time duration"),
                config.dead_time.mode,
            )
            links = match_triggers_to_truth(
                candidate_times_s,
                rendered_events,
                pre_s,
                post_s,
            )
            events_group.create_dataset(
                "trigger_event_links",
                data=links,
                dtype=TRIGGER_EVENT_LINK_DTYPE,
                maxshape=(None,),
                chunks=True,
                **compression,
            )

            link_counts = np.bincount(links["trigger_id"], minlength=candidate_indices.size)
            observed = np.empty(candidate_indices.size, dtype=OBSERVED_EVENT_DTYPE)
            polarity = int(_required(config.trigger.polarity, "trigger polarity"))
            timing_failures = 0
            for trigger_id, center in enumerate(candidate_indices):
                start = max(0, int(center) - pre_samples)
                stop = min(waveform.sample_count, int(center) + post_samples + 1)
                analog = np.asarray(analog_dataset[start:stop], dtype=np.float64)
                adc = np.asarray(adc_dataset[start:stop], dtype=np.uint16)
                saturation = np.asarray(saturation_dataset[start:stop], dtype=np.bool_)
                aligned = polarity * (analog - baseline_V)
                peak_local = int(np.argmax(aligned))
                peak_V = float(analog[peak_local] - baseline_V)
                peak_adc = int(np.max(adc) if polarity > 0 else np.min(adc))
                integral_V_s = float(
                    np.sum(
                        ((analog[:-1] - baseline_V) + (analog[1:] - baseline_V))
                        * (0.5 / waveform.sample_rate_hz),
                        dtype=np.float64,
                    )
                )
                rise_s = float("nan")
                fall_s = float("nan")
                try:
                    features = extract_pulse_features(
                        analog,
                        waveform.sample_rate_hz,
                        polarity,
                        baseline_V,
                    )
                    rise_s = features.rise_time_10_90_s
                    fall_s = features.fall_time_90_10_s
                except ValueError:
                    timing_failures += 1
                accepted = bool(dead_time.accepted[trigger_id])
                observed[trigger_id] = (
                    trigger_id,
                    candidate_times_s[trigger_id],
                    accepted,
                    b"none" if accepted else b"dead_time",
                    peak_adc,
                    peak_V,
                    integral_V_s,
                    rise_s,
                    fall_s,
                    bool(link_counts[trigger_id] > 1),
                    bool(np.any(saturation)),
                )
            events_group.create_dataset(
                "observed",
                data=observed,
                dtype=OBSERVED_EVENT_DTYPE,
                maxshape=(None,),
                chunks=True,
                **compression,
            )

            window_candidates = [
                (trigger_id, int(center))
                for trigger_id, center in enumerate(candidate_indices)
                if dead_time.accepted[trigger_id]
                and center >= pre_samples
                and center + post_samples < waveform.sample_count
            ][: simulation.max_windows]
            windows = handle.create_group("windows")
            window_adc = windows.create_dataset(
                "adc",
                shape=(len(window_candidates), window_length),
                maxshape=(None, window_length),
                dtype=np.uint16,
                chunks=(1, window_length),
                **compression,
            )
            window_metadata = np.empty(len(window_candidates), dtype=WINDOW_METADATA_DTYPE)
            for window_id, (trigger_id, center) in enumerate(window_candidates):
                start = center - pre_samples
                stop = center + post_samples + 1
                window_adc[window_id] = adc_dataset[start:stop]
                window_metadata[window_id] = (
                    window_id,
                    trigger_id,
                    start,
                    pre_samples,
                    waveform.sample_rate_hz,
                    bool(np.any(saturation_dataset[start:stop])),
                )
            windows.create_dataset(
                "metadata",
                data=window_metadata,
                dtype=WINDOW_METADATA_DTYPE,
                maxshape=(None,),
                chunks=True,
                **compression,
            )

            calibration = handle.create_group("calibration")
            calibration.attrs["parameter_status"] = simulation.parameter_status.value
            calibration.attrs["note"] = (
                "No measured calibration is embedded; synthetic_demo values are software-only."
            )
            statistics = handle.create_group("statistics")
            rendered_event_count = rendered_events.size
            accepted_count = int(np.count_nonzero(dead_time.accepted))
            false_trigger_count = int(np.count_nonzero(link_counts == 0))
            statistics.attrs["true_event_count"] = event_generator.event_count
            statistics.attrs["rendered_true_event_count"] = rendered_event_count
            statistics.attrs["trigger_candidate_count"] = candidate_indices.size
            statistics.attrs["accepted_trigger_count"] = accepted_count
            statistics.attrs["dead_time_rejected_count"] = candidate_indices.size - accepted_count
            statistics.attrs["false_trigger_count"] = false_trigger_count
            statistics.attrs["pileup_trigger_count"] = int(np.count_nonzero(link_counts > 1))
            statistics.attrs["saturated_sample_count"] = saturated_samples
            statistics.attrs["timing_feature_failure_count"] = timing_failures
            statistics.attrs["window_count"] = len(window_candidates)
            statistics.attrs["dead_time_loss_fraction"] = (
                1.0 - accepted_count / candidate_indices.size if candidate_indices.size else 0.0
            )
            statistics.attrs["trigger_efficiency"] = (
                np.unique(links["event_id"]).size / rendered_event_count
                if rendered_event_count
                else 0.0
            )
            statistics.attrs["compression"] = config.dataset.compression
        temporary_path.replace(path)
    except Exception:
        if temporary_path.exists():
            temporary_path.unlink()
        raise
    return path
