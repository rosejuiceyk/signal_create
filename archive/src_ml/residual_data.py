"""Physical-waveform patches with explicitly artificial Phase 6S residuals."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from he3sim.config import He3SimConfig, ParameterStatus, load_config
from he3sim.ml.residual_config import (
    ArtificialInterferenceConfig,
    SyntheticResidualRehearsalConfig,
)
from he3sim.synthesis.streaming import iter_waveform_blocks, prepare_waveform_simulation

FloatPatch = npt.NDArray[np.float32]
BoolPatch = npt.NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class SyntheticResidualPatch:
    """One independent synthetic run used as one bounded learning patch."""

    run_id: str
    split: str
    true_rate_cps: float
    sample_rate_hz: float
    seed: int
    physical_waveform_V: FloatPatch
    artificial_residual_V: FloatPatch
    target_waveform_V: FloatPatch
    event_guard_mask: BoolPatch
    true_event_count: int


def _patch_physical_config(
    base: He3SimConfig,
    rate_cps: float,
    sample_rate_hz: float,
    patch_samples: int,
    seed: int,
    run_id: str,
) -> He3SimConfig:
    payload = base.model_dump(mode="python")
    payload["metadata"]["run_name"] = run_id
    payload["metadata"]["seed"] = {
        "value": seed,
        "status": ParameterStatus.SYNTHETIC_DEMO.value,
        "notes": "Phase 6S independent synthetic-run seed.",
    }
    payload["simulation"]["true_rate_cps"] = {
        "value": rate_cps,
        "status": ParameterStatus.SYNTHETIC_DEMO.value,
        "notes": "Phase 6S synthetic rehearsal condition.",
    }
    payload["simulation"]["sample_rate_hz"] = {
        "value": sample_rate_hz,
        "status": ParameterStatus.SYNTHETIC_DEMO.value,
        "notes": "Phase 6S software grid, not a measured sampling axis.",
    }
    payload["observation"] = {
        "mode": "fixed_duration",
        "duration_s": {
            "value": (patch_samples - 1.5) / sample_rate_hz,
            "status": ParameterStatus.SYNTHETIC_DEMO.value,
        },
    }
    payload["waveform"]["max_samples_per_block"] = {
        "value": patch_samples,
        "status": ParameterStatus.SYNTHETIC_DEMO.value,
        "notes": "Bounded Phase 6S learning patch.",
    }
    return He3SimConfig.model_validate(payload)


def event_guard_mask(
    event_sample_indices: npt.NDArray[np.int64],
    patch_samples: int,
    guard_samples: int,
) -> BoolPatch:
    """Protect truth-event anchors without modifying the truth event table."""
    mask = np.zeros(patch_samples, dtype=np.bool_)
    for index in event_sample_indices:
        start = max(0, int(index) - guard_samples)
        stop = min(patch_samples, int(index) + guard_samples + 1)
        mask[start:stop] = True
    return mask


def _colored_noise(
    sample_count: int,
    rms_V: float,
    coefficient: float,
    rng: np.random.Generator,
) -> npt.NDArray[np.float64]:
    if rms_V == 0.0:
        return np.zeros(sample_count, dtype=np.float64)
    values = np.empty(sample_count, dtype=np.float64)
    values[0] = rng.normal(0.0, rms_V)
    innovation_rms = rms_V * math.sqrt(1.0 - coefficient * coefficient)
    innovations = rng.normal(0.0, innovation_rms, max(0, sample_count - 1))
    for index in range(1, sample_count):
        values[index] = coefficient * values[index - 1] + innovations[index - 1]
    return values


def artificial_interference(
    physical_waveform_V: FloatPatch,
    event_sample_indices: npt.NDArray[np.int64],
    event_polarities: npt.NDArray[np.int16],
    guard_mask: BoolPatch,
    true_rate_cps: float,
    seed: int,
    config: ArtificialInterferenceConfig,
) -> FloatPatch:
    """Create known disturbances in sample units, never measured-device parameters."""
    sample_count = physical_waveform_V.size
    rng = np.random.default_rng(np.random.SeedSequence([seed, 0x6A5C]))
    position = np.arange(sample_count, dtype=np.float64) / max(1, sample_count - 1)
    rate_coordinate = (math.log10(true_rate_cps) - 1.0) / 6.0
    baseline = config.baseline_wander_amplitude_V * (
        0.25 * rate_coordinate + np.sin(2.0 * np.pi * config.baseline_cycles_per_patch * position)
    )
    white = rng.normal(0.0, config.white_noise_rms_V, sample_count)
    colored = _colored_noise(
        sample_count,
        config.colored_noise_rms_V,
        config.colored_noise_ar,
        rng,
    )
    nonlinear = (
        config.nonlinear_tail_amplitude_V
        * np.tanh(np.asarray(physical_waveform_V, dtype=np.float64) / config.nonlinear_scale_V) ** 3
    )
    ringing = np.zeros(sample_count, dtype=np.float64)
    for sample_index, polarity in zip(event_sample_indices, event_polarities, strict=True):
        start = int(sample_index) + 1
        if start >= sample_count:
            continue
        offset = np.arange(1, sample_count - int(sample_index), dtype=np.float64)
        ringing[start:] += (
            int(polarity)
            * config.ringing_amplitude_V
            * np.exp(-offset / config.ringing_decay_samples)
            * np.sin(2.0 * np.pi * offset / config.ringing_period_samples)
        )
    residual = baseline + white + colored + nonlinear + ringing
    residual[guard_mask] = 0.0
    residual = np.clip(residual, -config.max_abs_residual_V, config.max_abs_residual_V)
    return np.asarray(residual, dtype=np.float32)


def _generate_patch(
    base_config: He3SimConfig,
    config: SyntheticResidualRehearsalConfig,
    split: str,
    rate_cps: float,
    run_index: int,
    seed: int,
) -> SyntheticResidualPatch:
    run_id = f"{split}-rate-{rate_cps:.12g}-run-{run_index:03d}"
    physical_config = _patch_physical_config(
        base_config,
        rate_cps,
        config.sample_rate_hz,
        config.patch_samples,
        seed,
        run_id,
    )
    simulation = prepare_waveform_simulation(
        physical_config,
        max_expected_events=100_000,
        max_waveform_samples=config.patch_samples,
    )
    physical = np.concatenate(
        [
            block.preclip_analog_samples_V
            for block in iter_waveform_blocks(simulation, physical_config)
            if block.preclip_analog_samples_V is not None
        ]
    )
    if physical.size != config.patch_samples:
        raise RuntimeError("physical simulator did not produce the configured patch length")
    event_indices = np.asarray(simulation.true_events.events["sample_index"], dtype=np.int64)
    polarities = np.asarray(simulation.true_events.events["polarity"], dtype=np.int16)
    guard = event_guard_mask(event_indices, config.patch_samples, config.event_guard_samples)
    physical_float = np.asarray(physical, dtype=np.float32)
    residual = artificial_interference(
        physical_float,
        event_indices,
        polarities,
        guard,
        rate_cps,
        seed,
        config.interference,
    )
    return SyntheticResidualPatch(
        run_id=run_id,
        split=split,
        true_rate_cps=rate_cps,
        sample_rate_hz=config.sample_rate_hz,
        seed=seed,
        physical_waveform_V=physical_float,
        artificial_residual_V=residual,
        target_waveform_V=np.asarray(physical_float + residual, dtype=np.float32),
        event_guard_mask=guard,
        true_event_count=int(simulation.true_events.events.size),
    )


def build_synthetic_residual_dataset(
    config: SyntheticResidualRehearsalConfig,
) -> dict[str, list[SyntheticResidualPatch]]:
    """Build independent synthetic-run splits through the audited physical API."""
    base_config = load_config(Path(config.physical_config_path))
    split_counts = {
        "train": config.training.train_runs_per_rate,
        "validation": config.training.validation_runs_per_rate,
        "test": config.training.test_runs_per_rate,
    }
    total = len(config.true_rates_cps) * sum(split_counts.values())
    sequences = np.random.SeedSequence(config.training.seed).spawn(total)
    seeds = [int(sequence.generate_state(1, dtype=np.uint32)[0]) for sequence in sequences]
    cursor = 0
    result: dict[str, list[SyntheticResidualPatch]] = {name: [] for name in split_counts}
    for split, count in split_counts.items():
        for rate_cps in config.true_rates_cps:
            for run_index in range(count):
                result[split].append(
                    _generate_patch(
                        base_config,
                        config,
                        split,
                        rate_cps,
                        run_index,
                        seeds[cursor],
                    )
                )
                cursor += 1
    return result
