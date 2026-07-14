"""Standard-rate ideal dead-time validation and bounded-memory analysis."""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from he3sim.acquisition.dead_time import apply_dead_time, theoretical_observed_rate_cps
from he3sim.config import DeadTimeMode, He3SimConfig
from he3sim.physics.arrivals import PoissonUniformArrivalGenerator
from he3sim.physics.rate_profiles import ConstantRateProfile
from he3sim.types import TRUE_EVENT_DTYPE

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
VALIDATION_EXPECTED_EVENTS_PER_REPLICATE = 2_000.0
MIN_REPLICATES = 30
MIN_RELATIVE_TOLERANCE = 0.03
SIGMA_MULTIPLIER = 6.0
EVENT_STREAM_CHUNK_EVENTS = 32_768


@dataclass(frozen=True, slots=True)
class DeadTimePoint:
    """One rate/mode comparison against the ideal analytic relation."""

    true_rate_cps: float
    mode: str
    duration_s: float
    generated_count: int
    accepted_count: int
    observed_rate_cps: float
    theoretical_rate_cps: float
    relative_error: float
    relative_tolerance: float
    passed: bool


@dataclass(frozen=True, slots=True)
class Phase3ValidationReport:
    """Complete standard-rate and memory-bound validation payload."""

    seed: int
    dead_time_duration_s: float
    replicates: int
    points: tuple[DeadTimePoint, ...]
    memory_analysis: dict[str, int | float | str]
    scan_elapsed_s: float
    generated_events_per_s: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible mapping."""
        return asdict(self)


def analyze_streaming_memory(
    config: He3SimConfig,
    max_expected_events: int,
    max_waveform_samples: int,
) -> dict[str, int | float | str]:
    """Return conservative allocation bounds independent of event-horizon block count."""
    if config.waveform.max_samples_per_block.value is None:
        raise ValueError("max_samples_per_block requires a value")
    block_samples = config.waveform.max_samples_per_block.value
    # Conservative live arrays: recursive sources/states/output, analog/noise/clipping,
    # ADC and masks. HDF5 compression has its own chunk buffer of comparable size.
    waveform_bytes_per_sample = 8 * 8 + 2 + 4
    waveform_block_bytes = block_samples * waveform_bytes_per_sample
    compression_buffer_bytes = block_samples * (4 + 2 + 1)
    event_chunk_bytes = EVENT_STREAM_CHUNK_EVENTS * TRUE_EVENT_DTYPE.itemsize
    association_buffer_bytes = max_expected_events * TRUE_EVENT_DTYPE.itemsize
    candidate_index_bound_bytes = max_waveform_samples * np.dtype(np.int64).itemsize
    conservative_peak_bytes = (
        waveform_block_bytes
        + compression_buffer_bytes
        + event_chunk_bytes
        + association_buffer_bytes
        + candidate_index_bound_bytes
    )
    return {
        "method": "conservative allocation bound from configured guards",
        "block_samples": block_samples,
        "waveform_block_bytes": waveform_block_bytes,
        "compression_buffer_bytes": compression_buffer_bytes,
        "event_stream_chunk_events": EVENT_STREAM_CHUNK_EVENTS,
        "event_stream_chunk_bytes": event_chunk_bytes,
        "max_rendered_association_events": max_expected_events,
        "association_buffer_bytes": association_buffer_bytes,
        "candidate_index_bound_bytes": candidate_index_bound_bytes,
        "conservative_peak_bytes": conservative_peak_bytes,
        "horizon_scaling": (
            "HDF5 rows and file size scale with horizon; event-only truth chunks and waveform "
            "blocks do not accumulate in RAM. Rendered association data remain capped by the "
            "explicit event and sample guards."
        ),
    }


def validate_phase3_physics(
    config: He3SimConfig,
    replicates: int = 60,
    max_expected_events: int = 1_000_000,
    max_waveform_samples: int = 10_000_000,
) -> Phase3ValidationReport:
    """Validate both ideal dead-time modes at all thirteen standard rates."""
    if replicates < MIN_REPLICATES:
        raise ValueError(f"replicates must be at least {MIN_REPLICATES}")
    if config.metadata.seed.value is None:
        raise ValueError("seed requires a value")
    if config.dead_time.duration_s.value is None:
        raise ValueError("dead-time duration requires a value")
    dead_time_s = config.dead_time.duration_s.value
    if dead_time_s <= 0.0:
        raise ValueError("Phase 3 validation requires positive dead time")
    seed_sequence = np.random.SeedSequence(config.metadata.seed.value)
    child_sequences = seed_sequence.spawn(len(STANDARD_RATES_CPS))
    generator = PoissonUniformArrivalGenerator()
    points: list[DeadTimePoint] = []
    total_generated_events = 0
    scan_start = time.perf_counter()
    for rate_cps, child in zip(STANDARD_RATES_CPS, child_sequences, strict=True):
        duration_s = VALIDATION_EXPECTED_EVENTS_PER_REPLICATE / rate_cps
        warmup_s = 10.0 * dead_time_s
        rng = np.random.default_rng(child)
        generated_total = 0
        accepted_totals = {
            DeadTimeMode.NONPARALYZABLE: 0,
            DeadTimeMode.PARALYZABLE: 0,
        }
        for _ in range(replicates):
            times_s = generator.sample(
                ConstantRateProfile(rate_cps),
                0.0,
                warmup_s + duration_s,
                rng,
            )
            measured = times_s >= warmup_s
            generated_total += int(np.count_nonzero(measured))
            for mode in accepted_totals:
                result = apply_dead_time(times_s, dead_time_s, mode)
                accepted_totals[mode] += int(np.count_nonzero(result.accepted & measured))
        total_duration_s = duration_s * replicates
        total_generated_events += generated_total
        for mode, accepted_count in accepted_totals.items():
            observed_rate_cps = accepted_count / total_duration_s
            theoretical_rate_cps = theoretical_observed_rate_cps(rate_cps, dead_time_s, mode)
            expected_accepted = theoretical_rate_cps * total_duration_s
            count_error = abs(accepted_count - expected_accepted)
            count_tolerance = SIGMA_MULTIPLIER * math.sqrt(expected_accepted + 1.0)
            denominator = max(expected_accepted, 1.0)
            relative_error = count_error / denominator
            tolerance = max(MIN_RELATIVE_TOLERANCE, count_tolerance / denominator)
            points.append(
                DeadTimePoint(
                    true_rate_cps=rate_cps,
                    mode=mode.value,
                    duration_s=duration_s,
                    generated_count=generated_total,
                    accepted_count=accepted_count,
                    observed_rate_cps=observed_rate_cps,
                    theoretical_rate_cps=theoretical_rate_cps,
                    relative_error=relative_error,
                    relative_tolerance=tolerance,
                    passed=count_error
                    <= max(
                        MIN_RELATIVE_TOLERANCE * expected_accepted,
                        count_tolerance,
                    ),
                )
            )
    scan_elapsed_s = time.perf_counter() - scan_start
    memory = analyze_streaming_memory(config, max_expected_events, max_waveform_samples)
    return Phase3ValidationReport(
        seed=config.metadata.seed.value,
        dead_time_duration_s=dead_time_s,
        replicates=replicates,
        points=tuple(points),
        memory_analysis=memory,
        scan_elapsed_s=scan_elapsed_s,
        generated_events_per_s=total_generated_events / scan_elapsed_s,
        passed=all(point.passed for point in points),
    )


def write_phase3_validation_report(
    output_directory: str | Path,
    report: Phase3ValidationReport,
) -> Path:
    """Write JSON and Markdown statistics, memory, and machine-local timing reports."""
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "phase03_validation.json"
    json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Phase 3 trigger/dead-time and streaming validation",
        "",
        f"- Result: `{'passed' if report.passed else 'failed'}`",
        f"- Seed: `{report.seed}`",
        f"- Dead time: `{report.dead_time_duration_s:.9g} s` (`synthetic_demo`)",
        f"- Replicates per rate: `{report.replicates}`",
        f"- Scan wall time on this machine: `{report.scan_elapsed_s:.6g} s`",
        f"- Generated-event throughput: `{report.generated_events_per_s:.6g} events/s`",
        "",
        "| True rate (cps) | Mode | Simulated observed (cps) | Theory (cps) | "
        "Rel. error | Tolerance | Pass |",
        "|---:|---|---:|---:|---:|---:|---|",
    ]
    for point in report.points:
        lines.append(
            f"| {point.true_rate_cps:.8g} | `{point.mode}` | "
            f"{point.observed_rate_cps:.8g} | {point.theoretical_rate_cps:.8g} | "
            f"{point.relative_error:.5g} | {point.relative_tolerance:.5g} | "
            f"{point.passed} |"
        )
    lines.extend(
        [
            "",
            "## Memory analysis",
            "",
            "- Conservative peak bound: "
            f"`{report.memory_analysis['conservative_peak_bytes']} bytes`",
            f"- Waveform block: `{report.memory_analysis['waveform_block_bytes']} bytes`",
            "- Truth-event stream chunk: "
            f"`{report.memory_analysis['event_stream_chunk_bytes']} bytes`",
            f"- Analysis: {report.memory_analysis['horizon_scaling']}",
            "",
            "The dead-time scan is event-level and does not delete or render truth events. "
            "The dataset "
            "path separately applies the configured mode only to waveform-trigger candidates.",
            "",
        ]
    )
    markdown_path = output / "phase03_validation.md"
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path
