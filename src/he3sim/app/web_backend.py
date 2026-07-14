"""Testable backend for bounded local Web waveform generation."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import h5py  # type: ignore[import-untyped]
import numpy as np
import yaml

from he3sim.analysis.waveform_plot import plot_waveform_hdf5
from he3sim.config import (
    MAX_TRUE_RATE_CPS,
    MIN_TRUE_RATE_CPS,
    He3SimConfig,
    config_hash,
)
from he3sim.io.hdf5 import write_waveform_hdf5
from he3sim.synthesis.renderers import waveform_sample_count
from he3sim.synthesis.streaming import prepare_waveform_simulation

MIN_SAMPLE_RATE_HZ = 100.0e6
MAX_SAMPLE_RATE_HZ = 250.0e6
MAX_WEB_WAVEFORM_SAMPLES = 5_000_000
MAX_WEB_EXPECTED_EVENTS = 1_000_000
WAVEFORM_BYTES_PER_SAMPLE = 11


@dataclass(frozen=True, slots=True)
class InteractiveWaveformRequest:
    """User-controlled inputs allowed by the Phase 3.5 local interface."""

    true_rate_cps: float
    sample_rate_hz: float
    duration_s: float
    seed: int


@dataclass(frozen=True, slots=True)
class InteractiveDurationLimit:
    """Observation-time limits implied by interactive sample and event guards."""

    maximum_duration_s: float
    sample_limited_duration_s: float
    event_limited_duration_s: float
    limiting_constraint: str


@dataclass(frozen=True, slots=True)
class WaveformResourceEstimate:
    """Preflight estimate for one bounded interactive waveform request."""

    expected_event_count: float
    sample_count: int
    sample_interval_s: float
    estimated_waveform_payload_bytes: int


@dataclass(frozen=True, slots=True)
class InteractiveRunResult:
    """Paths and verified metadata for one generated interactive run."""

    run_directory: Path
    config_path: Path
    waveform_path: Path
    csv_path: Path
    image_path: Path
    sampling_info_path: Path
    estimate: WaveformResourceEstimate
    actual_event_count: int
    renderer: str
    parameter_status: str
    config_hash: str


def maximum_interactive_duration(
    true_rate_cps: float,
    sample_rate_hz: float,
    *,
    max_waveform_samples: int = MAX_WEB_WAVEFORM_SAMPLES,
    max_expected_events: int = MAX_WEB_EXPECTED_EVENTS,
) -> InteractiveDurationLimit:
    """Return the safe observation-time limit for current rate and sampling inputs."""
    if (
        not math.isfinite(true_rate_cps)
        or not MIN_TRUE_RATE_CPS <= true_rate_cps <= MAX_TRUE_RATE_CPS
    ):
        raise ValueError("true_rate_cps must be finite and within [10, 1e7]")
    if (
        not math.isfinite(sample_rate_hz)
        or not MIN_SAMPLE_RATE_HZ <= sample_rate_hz <= MAX_SAMPLE_RATE_HZ
    ):
        raise ValueError("sample_rate_hz must be finite and within [100e6, 250e6]")
    if max_waveform_samples <= 1 or max_expected_events <= 0:
        raise ValueError("interactive resource limits must be positive")
    sample_limited_duration_s = math.nextafter(
        (max_waveform_samples - 1) / sample_rate_hz,
        0.0,
    )
    event_limited_duration_s = max_expected_events / true_rate_cps
    if sample_limited_duration_s <= event_limited_duration_s:
        limiting_constraint = "sample_count"
        maximum_duration_s = sample_limited_duration_s
    else:
        limiting_constraint = "expected_event_count"
        maximum_duration_s = event_limited_duration_s
    return InteractiveDurationLimit(
        maximum_duration_s=maximum_duration_s,
        sample_limited_duration_s=sample_limited_duration_s,
        event_limited_duration_s=event_limited_duration_s,
        limiting_constraint=limiting_constraint,
    )


def estimate_waveform_resources(
    request: InteractiveWaveformRequest,
    *,
    max_waveform_samples: int = MAX_WEB_WAVEFORM_SAMPLES,
    max_expected_events: int = MAX_WEB_EXPECTED_EVENTS,
) -> WaveformResourceEstimate:
    """Validate an interactive request and return its deterministic resource estimate."""
    values = (request.true_rate_cps, request.sample_rate_hz, request.duration_s)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("rate, sample rate, and duration must be finite")
    if not MIN_TRUE_RATE_CPS <= request.true_rate_cps <= MAX_TRUE_RATE_CPS:
        raise ValueError("true_rate_cps must be within [10, 1e7]")
    if not MIN_SAMPLE_RATE_HZ <= request.sample_rate_hz <= MAX_SAMPLE_RATE_HZ:
        raise ValueError("sample_rate_hz must be within [100e6, 250e6]")
    if request.duration_s <= 0.0:
        raise ValueError("duration_s must be positive")
    if request.seed < 0:
        raise ValueError("seed must be non-negative")
    if max_waveform_samples <= 0 or max_expected_events <= 0:
        raise ValueError("resource limits must be positive")

    sample_count = waveform_sample_count(request.duration_s, request.sample_rate_hz)
    expected_event_count = request.true_rate_cps * request.duration_s
    if sample_count > max_waveform_samples:
        approximate_max_duration_ms = (max_waveform_samples - 1) / request.sample_rate_hz * 1.0e3
        raise ValueError(
            f"采样点数 {sample_count:,} 超过本地网页单次上限 "
            f"{max_waveform_samples:,}；当前采样率下观察时间应小于约 "
            f"{approximate_max_duration_ms:.3f} ms"
        )
    if expected_event_count > max_expected_events:
        raise ValueError(
            f"预期事件数 {expected_event_count:,.1f} 超过本地网页单次上限 "
            f"{max_expected_events:,}；请缩短观察时间或降低计数率"
        )
    return WaveformResourceEstimate(
        expected_event_count=expected_event_count,
        sample_count=sample_count,
        sample_interval_s=1.0 / request.sample_rate_hz,
        estimated_waveform_payload_bytes=sample_count * WAVEFORM_BYTES_PER_SAMPLE,
    )


def build_interactive_config(
    base_config_path: str | Path,
    request: InteractiveWaveformRequest,
    *,
    run_name: str,
) -> He3SimConfig:
    """Derive a validated run config without modifying the selected base YAML."""
    path = Path(base_config_path)
    with path.open("r", encoding="utf-8") as stream:
        payload: Any = yaml.safe_load(stream)
    if not isinstance(payload, dict):
        raise ValueError("base configuration root must be a YAML mapping")

    payload["metadata"]["run_name"] = run_name
    payload["metadata"]["description"] = (
        "Phase 3.5 local Web run. User-controlled operating inputs are recorded; "
        "all detector and electronics model values retain their base evidence status."
    )
    payload["metadata"]["seed"] = {
        "value": request.seed,
        "status": "synthetic_demo",
        "notes": "User-selected reproducibility seed for a synthetic local Web run.",
    }
    payload["simulation"]["true_rate_cps"] = {
        "value": request.true_rate_cps,
        "status": "synthetic_demo",
        "notes": "User-selected operating input; not a measured detector rate.",
    }
    payload["simulation"]["sample_rate_hz"] = {
        "value": request.sample_rate_hz,
        "status": "synthetic_demo",
        "notes": "User-selected software sampling grid; not a device specification.",
    }
    payload["observation"] = {
        "mode": "fixed_duration",
        "duration_s": {
            "value": request.duration_s,
            "status": "synthetic_demo",
            "notes": "User-selected fixed observation time for local waveform generation.",
        },
    }
    return He3SimConfig.model_validate(payload)


def _write_run_config(path: Path, config: He3SimConfig) -> None:
    """Write the exact validated run configuration as UTF-8 YAML."""
    payload = config.model_dump(mode="json", exclude_none=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        yaml.safe_dump(payload, stream, allow_unicode=True, sort_keys=False)


def _run_identifier(now: datetime | None = None) -> str:
    """Return a sortable, collision-resistant local run identifier."""
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"web-{timestamp}-{uuid4().hex[:8]}"


def write_waveform_csv(
    waveform_path: str | Path,
    output_path: str | Path,
    *,
    chunk_size: int = 65_536,
) -> Path:
    """Stream analog waveform samples to a two-column UTF-8 CSV file."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    source = Path(waveform_path)
    destination = Path(output_path)
    if destination.suffix.lower() != ".csv":
        raise ValueError("waveform CSV output must use the .csv extension")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".csv.tmp")

    try:
        with (
            h5py.File(source, "r") as handle,
            temporary.open("w", encoding="utf-8", newline="\n") as stream,
        ):
            if "blocks/analog_samples" not in handle:
                raise ValueError("waveform HDF5 does not contain analog voltage samples")
            analog = handle["blocks/analog_samples"]
            if analog.ndim != 1:
                raise ValueError("analog voltage samples must be one-dimensional")
            sample_rate_hz = float(handle["metadata"].attrs["sample_rate_hz"])
            if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
                raise ValueError("waveform HDF5 has an invalid sample rate")

            stream.write("time_s,voltage_V\n")
            sample_count = int(analog.shape[0])
            for start in range(0, sample_count, chunk_size):
                stop = min(start + chunk_size, sample_count)
                indices = np.arange(start, stop, dtype=np.float64)
                times_s = indices / sample_rate_hz
                voltages_V = np.asarray(analog[start:stop], dtype=np.float32)
                rows = np.column_stack((times_s, voltages_V))
                np.savetxt(stream, rows, delimiter=",", fmt=("%.17g", "%.9g"))
        temporary.replace(destination)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return destination


def generate_interactive_waveform(
    request: InteractiveWaveformRequest,
    *,
    base_config_path: str | Path,
    output_root: str | Path,
    max_waveform_samples: int = MAX_WEB_WAVEFORM_SAMPLES,
    max_expected_events: int = MAX_WEB_EXPECTED_EVENTS,
) -> InteractiveRunResult:
    """Generate HDF5, CSV, PNG, YAML, and JSON with the existing core pipeline."""
    estimate = estimate_waveform_resources(
        request,
        max_waveform_samples=max_waveform_samples,
        max_expected_events=max_expected_events,
    )
    run_name = _run_identifier()
    run_directory = Path(output_root) / run_name
    run_directory.mkdir(parents=True, exist_ok=False)
    config = build_interactive_config(base_config_path, request, run_name=run_name)

    config_path = run_directory / "run_config.yaml"
    waveform_path = run_directory / "waveform.h5"
    csv_path = run_directory / "waveform.csv"
    image_path = run_directory / "waveform.png"
    sampling_info_path = run_directory / "sampling_info.json"
    _write_run_config(config_path, config)

    simulation = prepare_waveform_simulation(
        config,
        max_expected_events=max_expected_events,
        max_waveform_samples=max_waveform_samples,
    )
    write_waveform_hdf5(waveform_path, simulation, config)
    plot_waveform_hdf5(waveform_path, image_path)
    write_waveform_csv(waveform_path, csv_path)

    digest = config_hash(config)
    info = {
        "schema_version": "1",
        "run_name": run_name,
        "inputs": {
            "true_rate_cps": request.true_rate_cps,
            "sample_rate_hz": request.sample_rate_hz,
            "duration_s": request.duration_s,
            "seed": request.seed,
        },
        "sampling": {
            "sample_interval_s": estimate.sample_interval_s,
            "sample_count": simulation.sample_count,
            "time_origin_s": 0.0,
            "sample_time_formula": "t_s = sample_index / sample_rate_hz",
            "preclip_analog_dataset": "/blocks/preclip_analog_samples",
            "analog_dataset": "/blocks/analog_samples",
            "adc_dataset": "/blocks/adc_samples",
            "saturation_dataset": "/blocks/saturation_mask",
        },
        "events": {
            "expected_count": estimate.expected_event_count,
            "actual_count": int(simulation.true_events.events.size),
            "truth_dataset": "/events/true",
        },
        "resources": {
            "estimated_waveform_payload_bytes": (estimate.estimated_waveform_payload_bytes),
            "waveform_hdf5_bytes": waveform_path.stat().st_size,
            "waveform_csv_bytes": csv_path.stat().st_size,
            "waveform_png_bytes": image_path.stat().st_size,
        },
        "provenance": {
            "renderer": simulation.renderer.value,
            "parameter_status": simulation.parameter_status.value,
            "config_hash": digest,
            "model_notice": (
                "Synthetic demonstration only; not a calibrated detector, "
                "preamplifier, ADC, or oscilloscope result."
            ),
        },
        "artifacts": {
            "config": config_path.name,
            "waveform_hdf5": waveform_path.name,
            "waveform_csv": csv_path.name,
            "waveform_image": image_path.name,
            "sampling_info": sampling_info_path.name,
        },
    }
    with sampling_info_path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(info, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")

    return InteractiveRunResult(
        run_directory=run_directory,
        config_path=config_path,
        waveform_path=waveform_path,
        csv_path=csv_path,
        image_path=image_path,
        sampling_info_path=sampling_info_path,
        estimate=estimate,
        actual_event_count=int(simulation.true_events.events.size),
        renderer=simulation.renderer.value,
        parameter_status=simulation.parameter_status.value,
        config_hash=digest,
    )


def read_sample_rows(
    waveform_path: str | Path,
    *,
    row_count: int = 12,
) -> list[dict[str, int | float | bool]]:
    """Read a small leading sample table for interactive inspection."""
    if row_count <= 0 or row_count > 1_000:
        raise ValueError("row_count must be within [1, 1000]")
    with h5py.File(Path(waveform_path), "r") as handle:
        metadata = handle["metadata"]
        sample_rate_hz = float(metadata.attrs["sample_rate_hz"])
        analog = handle["blocks/analog_samples"]
        adc = handle["blocks/adc_samples"]
        saturation = handle["blocks/saturation_mask"]
        count = min(row_count, int(analog.shape[0]))
        analog_values = np.asarray(analog[:count], dtype=np.float64)
        adc_values = np.asarray(adc[:count], dtype=np.uint16)
        saturation_values = np.asarray(saturation[:count], dtype=np.bool_)
    return [
        {
            "sample_index": index,
            "t_s": index / sample_rate_hz,
            "analog_V": float(analog_values[index]),
            "adc_code": int(adc_values[index]),
            "is_saturated": bool(saturation_values[index]),
        }
        for index in range(count)
    ]


def estimate_as_dict(estimate: WaveformResourceEstimate) -> dict[str, int | float]:
    """Return an estimate in a stable JSON-compatible form for the UI."""
    return asdict(estimate)
