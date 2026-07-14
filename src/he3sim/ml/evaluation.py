"""Strict statistical and performance comparison for the Phase 5 research model."""

from __future__ import annotations

import csv
import json
import time
import tracemalloc
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import numpy as np
import numpy.typing as npt
import torch

from he3sim.config import config_hash, load_config
from he3sim.ml.config import EventModelEvaluationConfig, ml_config_hash
from he3sim.ml.data import EventWindow, ExactPhysicsWindowSampler
from he3sim.ml.training import (
    load_event_model_checkpoint,
    resolve_torch_device,
    synchronize_device,
)


@dataclass(frozen=True, slots=True)
class RateComparison:
    """Metrics and threshold decision at one held-out or standard rate."""

    true_rate_cps: float
    split: str
    exact_mean_count: float
    model_mean_count: float
    model_rate_relative_bias: float
    exact_fano: float
    model_fano: float
    model_fano_error: float
    interval_ks: float
    model_interval_lag1: float
    event_type_tv: float
    energy_quantile_error: float
    amplitude_quantile_error: float
    tau_quantile_relative_error: float
    energy_amplitude_correlation_error: float
    illegal_event_count: int
    passed: bool


@dataclass(frozen=True, slots=True)
class EvaluationArtifacts:
    """Comparison output paths and the non-promotion conclusion."""

    report_path: Path
    json_path: Path
    csv_path: Path
    statistical_match: bool
    model_status: str
    exact_events_per_second: float
    model_events_per_second: float
    speed_ratio_model_over_exact: float


def _event_window_from_model(
    events: npt.NDArray[np.void], true_rate_cps: float, duration_s: float
) -> EventWindow:
    return EventWindow(
        true_rate_cps=true_rate_cps,
        duration_s=duration_s,
        times_s=np.asarray(events["t_s"], dtype=np.float64),
        energy_dep_keV=np.asarray(events["energy_dep_keV"], dtype=np.float64),
        component_id=np.asarray(events["spectrum_component_id"], dtype=np.int64),
        amplitude_peak_V=np.asarray(events["amplitude_peak_V"], dtype=np.float64),
        tau_r_s=np.asarray(events["tau_r_s"], dtype=np.float64),
        tau_d_s=np.asarray(events["tau_d_s"], dtype=np.float64),
    )


def _pooled_intervals(windows: Sequence[EventWindow]) -> npt.NDArray[np.float64]:
    values = [np.diff(np.concatenate(([0.0], window.times_s))) for window in windows]
    nonempty = [value for value in values if value.size]
    return np.concatenate(nonempty) if nonempty else np.empty(0, dtype=np.float64)


def _lag1_correlation(windows: Sequence[EventWindow]) -> float:
    left: list[npt.NDArray[np.float64]] = []
    right: list[npt.NDArray[np.float64]] = []
    for window in windows:
        intervals = np.diff(np.concatenate(([0.0], window.times_s)))
        if intervals.size >= 2:
            left.append(intervals[:-1])
            right.append(intervals[1:])
    if not left:
        return 0.0
    x = np.concatenate(left)
    y = np.concatenate(right)
    if np.std(x) == 0.0 or np.std(y) == 0.0:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def _ks_distance(first: npt.NDArray[np.float64], second: npt.NDArray[np.float64]) -> float:
    if first.size == 0 or second.size == 0:
        return 1.0
    first_sorted = np.sort(first)
    second_sorted = np.sort(second)
    values = np.concatenate((first_sorted, second_sorted))
    first_cdf = np.searchsorted(first_sorted, values, side="right") / first_sorted.size
    second_cdf = np.searchsorted(second_sorted, values, side="right") / second_sorted.size
    return float(np.max(np.abs(first_cdf - second_cdf)))


def _flatten(windows: Sequence[EventWindow], field: str) -> npt.NDArray[np.float64]:
    arrays = [np.asarray(getattr(window, field), dtype=np.float64) for window in windows]
    nonempty = [array for array in arrays if array.size]
    return np.concatenate(nonempty) if nonempty else np.empty(0, dtype=np.float64)


def _quantile_error(exact: npt.NDArray[np.float64], model: npt.NDArray[np.float64]) -> float:
    if exact.size == 0 or model.size == 0:
        return float("inf")
    probabilities = np.linspace(0.01, 0.99, 99)
    exact_quantiles = np.quantile(exact, probabilities)
    model_quantiles = np.quantile(model, probabilities)
    scale = max(float(np.quantile(exact, 0.95) - np.quantile(exact, 0.05)), 1.0e-12)
    return float(np.mean(np.abs(exact_quantiles - model_quantiles)) / scale)


def _relative_quantile_error(
    exact: npt.NDArray[np.float64], model: npt.NDArray[np.float64]
) -> float:
    if exact.size == 0 or model.size == 0:
        return float("inf")
    probabilities = np.linspace(0.01, 0.99, 99)
    exact_quantiles = np.quantile(exact, probabilities)
    model_quantiles = np.quantile(model, probabilities)
    scale = max(abs(float(np.median(exact))), 1.0e-30)
    return float(np.mean(np.abs(exact_quantiles - model_quantiles)) / scale)


def _component_proportions(windows: Sequence[EventWindow]) -> npt.NDArray[np.float64]:
    components = [window.component_id for window in windows if window.component_id.size]
    if not components:
        return np.zeros(4, dtype=np.float64)
    counts = np.bincount(np.concatenate(components), minlength=4).astype(np.float64)
    return counts / np.sum(counts)


def _energy_amplitude_correlation(windows: Sequence[EventWindow]) -> float:
    energy = _flatten(windows, "energy_dep_keV")
    amplitude = _flatten(windows, "amplitude_peak_V")
    if energy.size < 2 or np.std(energy) == 0.0 or np.std(amplitude) == 0.0:
        return 0.0
    return float(np.corrcoef(energy, amplitude)[0, 1])


def _fano(counts: npt.NDArray[np.float64]) -> float:
    mean = float(np.mean(counts))
    return float(np.var(counts, ddof=1) / mean) if mean > 0.0 and counts.size > 1 else 0.0


def _illegal_count(windows: Sequence[EventWindow]) -> int:
    illegal = 0
    for window in windows:
        illegal += int(np.count_nonzero(~np.isfinite(window.times_s)))
        illegal += int(np.count_nonzero(np.diff(window.times_s) <= 0.0))
        illegal += int(
            np.count_nonzero((window.times_s < 0.0) | (window.times_s >= window.duration_s))
        )
        illegal += int(np.count_nonzero(~np.isfinite(window.energy_dep_keV)))
        illegal += int(np.count_nonzero(window.energy_dep_keV < 0.0))
        illegal += int(np.count_nonzero(~np.isin(window.component_id, [0, 1, 2, 3])))
        illegal += int(np.count_nonzero(~np.isfinite(window.amplitude_peak_V)))
        illegal += int(np.count_nonzero(window.amplitude_peak_V <= 0.0))
        illegal += int(np.count_nonzero(window.tau_r_s <= 0.0))
        illegal += int(np.count_nonzero(window.tau_d_s <= window.tau_r_s))
    return illegal


def _rate_comparison(
    rate: float,
    split: str,
    exact_windows: Sequence[EventWindow],
    model_windows: Sequence[EventWindow],
    config: EventModelEvaluationConfig,
) -> RateComparison:
    exact_counts = np.asarray([window.count for window in exact_windows], dtype=np.float64)
    model_counts = np.asarray([window.count for window in model_windows], dtype=np.float64)
    exact_fano = _fano(exact_counts)
    model_fano = _fano(model_counts)
    rate_bias = abs(float(np.mean(model_counts)) / config.expected_events_per_window - 1.0)
    interval_ks = _ks_distance(_pooled_intervals(exact_windows), _pooled_intervals(model_windows))
    lag1 = _lag1_correlation(model_windows)
    type_tv = 0.5 * float(
        np.sum(
            np.abs(_component_proportions(exact_windows) - _component_proportions(model_windows))
        )
    )
    energy_error = _quantile_error(
        _flatten(exact_windows, "energy_dep_keV"),
        _flatten(model_windows, "energy_dep_keV"),
    )
    amplitude_error = _quantile_error(
        _flatten(exact_windows, "amplitude_peak_V"),
        _flatten(model_windows, "amplitude_peak_V"),
    )
    tau_error = max(
        _relative_quantile_error(
            _flatten(exact_windows, "tau_r_s"), _flatten(model_windows, "tau_r_s")
        ),
        _relative_quantile_error(
            _flatten(exact_windows, "tau_d_s"), _flatten(model_windows, "tau_d_s")
        ),
    )
    correlation_error = abs(
        _energy_amplitude_correlation(exact_windows) - _energy_amplitude_correlation(model_windows)
    )
    illegal = _illegal_count(model_windows)
    thresholds = config.thresholds
    passed = (
        rate_bias <= thresholds.maximum_rate_relative_bias
        and abs(model_fano - 1.0) <= thresholds.maximum_fano_error
        and interval_ks <= thresholds.maximum_interval_ks
        and abs(lag1) <= thresholds.maximum_interval_lag1_abs
        and type_tv <= thresholds.maximum_event_type_tv
        and energy_error <= thresholds.maximum_energy_quantile_error
        and amplitude_error <= thresholds.maximum_amplitude_quantile_error
        and tau_error <= thresholds.maximum_tau_quantile_relative_error
        and correlation_error <= thresholds.maximum_energy_amplitude_correlation_error
        and illegal == 0
    )
    return RateComparison(
        true_rate_cps=rate,
        split=split,
        exact_mean_count=float(np.mean(exact_counts)),
        model_mean_count=float(np.mean(model_counts)),
        model_rate_relative_bias=rate_bias,
        exact_fano=exact_fano,
        model_fano=model_fano,
        model_fano_error=abs(model_fano - 1.0),
        interval_ks=interval_ks,
        model_interval_lag1=lag1,
        event_type_tv=type_tv,
        energy_quantile_error=energy_error,
        amplitude_quantile_error=amplitude_error,
        tau_quantile_relative_error=tau_error,
        energy_amplitude_correlation_error=correlation_error,
        illegal_event_count=illegal,
        passed=passed,
    )


def _write_report(
    output_directory: Path,
    payload: dict[str, object],
    comparisons: Sequence[RateComparison],
) -> tuple[Path, Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "phase05_comparison.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    csv_path = output_directory / "phase05_rate_metrics.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(comparisons[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(comparison) for comparison in comparisons)
    report_path = output_directory / "phase05_comparison.md"
    rows = "\n".join(
        f"| {item.true_rate_cps:.8g} | {item.split} | {item.model_rate_relative_bias:.4f} | "
        f"{item.model_fano:.4f} | {item.interval_ks:.4f} | {item.event_type_tv:.4f} | "
        f"{item.energy_quantile_error:.4f} | {item.amplitude_quantile_error:.4f} | "
        f"{item.tau_quantile_relative_error:.4f} | {item.illegal_event_count} | "
        f"{'pass' if item.passed else 'fail'} |"
        for item in comparisons
    )
    exact_throughput = cast(float, payload["exact_events_per_second"])
    model_throughput = cast(float, payload["model_events_per_second"])
    speed_ratio = cast(float, payload["speed_ratio_model_over_exact"])
    report_path.write_text(
        f"""# Phase 5 exact-baseline comparison

- Model status: `experimental`
- Statistical match: `{payload["statistical_match"]}`
- Default generator: `exact_poisson_parametric_spectrum`
- Promotion recommended: `false`
- Exact throughput: `{exact_throughput:.8g}` events/s
- Model throughput: `{model_throughput:.8g}` events/s
- Model/exact speed ratio: `{speed_ratio:.8g}`
- Peak Python traced memory: `{payload["peak_python_bytes"]}` bytes
- Peak CUDA allocation: `{payload["peak_cuda_allocated_bytes"]}` bytes

The exact generator remains the default even if every research threshold passes. The network is
trained only on synthetic demo data and cannot be promoted without a separate scientific decision
and future real-data evidence.

| rate | split | bias | Fano | KS | type TV | E err | A err | tau err | bad | result |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
{rows}
""",
        encoding="utf-8",
    )
    return report_path, json_path, csv_path


def compare_event_model(
    config: EventModelEvaluationConfig,
    output_directory: str | Path,
) -> EvaluationArtifacts:
    """Compare a local checkpoint to exact physics at standard and interpolation rates."""
    output_path = Path(output_directory)
    device = resolve_torch_device(config.device)
    model, checkpoint = load_event_model_checkpoint(config.checkpoint_path, device)
    base_config = load_config(config.base_config_path)
    base_hash = config_hash(base_config)
    if checkpoint["base_config_hash"] != base_hash:
        raise ValueError("evaluation base config does not match checkpoint base config")
    exact_sampler = ExactPhysicsWindowSampler(base_config)
    exact_rng = np.random.default_rng(config.seed)
    model_seed_rng = np.random.default_rng(config.seed + 1)
    comparisons: list[RateComparison] = []
    exact_total_events = 0
    model_total_events = 0
    exact_elapsed_s = 0.0
    model_elapsed_s = 0.0
    tracemalloc.start()
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    standard = set(config.standard_rates_cps)
    for rate in config.standard_rates_cps + config.interpolation_rates_cps:
        duration = config.expected_events_per_window / rate
        exact_windows: list[EventWindow] = []
        exact_started = time.perf_counter()
        for _ in range(config.replicates_per_rate):
            exact_windows.append(
                exact_sampler.sample(rate, duration, exact_rng, config.max_events_per_window)
            )
        exact_elapsed_s += time.perf_counter() - exact_started
        exact_total_events += sum(window.count for window in exact_windows)

        model_windows: list[EventWindow] = []
        synchronize_device(device)
        model_started = time.perf_counter()
        for _ in range(config.replicates_per_rate):
            seed = int(model_seed_rng.integers(0, np.iinfo(np.int32).max))
            events = model.generate(
                rate,
                duration,
                seed=seed,
                max_events=config.max_events_per_window,
            )
            model_windows.append(_event_window_from_model(events, rate, duration))
        synchronize_device(device)
        model_elapsed_s += time.perf_counter() - model_started
        model_total_events += sum(window.count for window in model_windows)
        comparisons.append(
            _rate_comparison(
                rate,
                "standard" if rate in standard else "interpolation",
                exact_windows,
                model_windows,
                config,
            )
        )
    _, peak_python_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    peak_cuda_bytes = int(torch.cuda.max_memory_allocated(device)) if device.type == "cuda" else 0
    exact_throughput = exact_total_events / max(exact_elapsed_s, 1.0e-12)
    model_throughput = model_total_events / max(model_elapsed_s, 1.0e-12)
    speed_ratio = model_throughput / max(exact_throughput, 1.0e-12)
    statistical_match = all(comparison.passed for comparison in comparisons)
    payload: dict[str, object] = {
        "model_status": "experimental",
        "default_generator": "exact_poisson_parametric_spectrum",
        "promotion_recommended": False,
        "statistical_match": statistical_match,
        "device": str(device),
        "torch_version": str(torch.__version__),
        "cuda_available": torch.cuda.is_available(),
        "cuda_device_name": (torch.cuda.get_device_name(device) if device.type == "cuda" else None),
        "base_config_hash": base_hash,
        "evaluation_config_hash": ml_config_hash(config),
        "checkpoint_training_config_hash": checkpoint["training_config_hash"],
        "exact_total_events": exact_total_events,
        "model_total_events": model_total_events,
        "exact_elapsed_s": exact_elapsed_s,
        "model_elapsed_s": model_elapsed_s,
        "exact_events_per_second": exact_throughput,
        "model_events_per_second": model_throughput,
        "speed_ratio_model_over_exact": speed_ratio,
        "peak_python_bytes": peak_python_bytes,
        "peak_cuda_allocated_bytes": peak_cuda_bytes,
        "thresholds": config.thresholds.model_dump(mode="json"),
        "comparisons": [asdict(comparison) for comparison in comparisons],
    }
    report_path, json_path, csv_path = _write_report(output_path, payload, comparisons)
    return EvaluationArtifacts(
        report_path=report_path,
        json_path=json_path,
        csv_path=csv_path,
        statistical_match=statistical_match,
        model_status="experimental",
        exact_events_per_second=exact_throughput,
        model_events_per_second=model_throughput,
        speed_ratio_model_over_exact=speed_ratio,
    )
