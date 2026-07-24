"""Pulse-counting neutron-noise estimators for the pure-prompt Phase B model."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal

import numpy as np
import numpy.typing as npt
from scipy.optimize import least_squares  # type: ignore[import-untyped]
from scipy.signal import welch  # type: ignore[import-untyped]

MethodName = Literal["Rossi-alpha", "Feynman-alpha", "PSD", "Continuous-VTM"]


@dataclass(frozen=True, slots=True)
class AlphaFit:
    """One fitted alpha value and its uncertainty accounting."""

    method: MethodName
    alpha_per_s: float
    alpha_std_per_s: float
    naive_alpha_std_per_s: float
    amplitude: float
    baseline: float
    r_squared: float
    bootstrap_alpha_per_s: npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class NoiseCurve:
    """Precomputed curve values and the corresponding fitted model."""

    x: npt.NDArray[np.float64]
    observed: npt.NDArray[np.float64]
    fitted: npt.NDArray[np.float64]
    fit: AlphaFit


@dataclass(frozen=True, slots=True)
class NoiseAnalysis:
    """Rossi, Feynman, and PSD curves evaluated from the same event stream."""

    rossi: NoiseCurve
    feynman: NoiseCurve
    psd: NoiseCurve
    duration_s: float
    event_count: int
    observed_rate_cps: float


def rossi_model(
    lag_s: npt.ArrayLike, alpha_per_s: float, amplitude: float, baseline: float
) -> npt.NDArray[np.float64]:
    """Evaluate ``B + A exp(-alpha |tau|)``."""
    lag = np.asarray(lag_s, dtype=np.float64)
    return np.asarray(baseline + amplitude * np.exp(-alpha_per_s * np.abs(lag)), dtype=np.float64)


def feynman_model(
    gate_width_s: npt.ArrayLike, alpha_per_s: float, y_inf: float
) -> npt.NDArray[np.float64]:
    """Evaluate the pure-prompt single-exponential Feynman-Y model."""
    gate = np.asarray(gate_width_s, dtype=np.float64)
    argument = alpha_per_s * gate
    shape = 1.0 - (-np.expm1(-argument)) / argument
    return np.asarray(y_inf * shape, dtype=np.float64)


def psd_model(
    frequency_hz: npt.ArrayLike, alpha_per_s: float, y_inf: float, level: float
) -> npt.NDArray[np.float64]:
    """Evaluate a white level plus a zero-frequency Lorentzian excess."""
    omega = 2.0 * np.pi * np.asarray(frequency_hz, dtype=np.float64)
    return level * (1.0 + y_inf * alpha_per_s**2 / (alpha_per_s**2 + omega**2))


def _validate_times(times_s: npt.ArrayLike, duration_s: float) -> npt.NDArray[np.float64]:
    values = np.asarray(times_s, dtype=np.float64)
    if values.ndim != 1 or np.any(~np.isfinite(values)):
        raise ValueError("times_s must be a finite one-dimensional array")
    if not np.isfinite(duration_s) or duration_s <= 0.0:
        raise ValueError("duration_s must be finite and positive")
    if values.size and (values[0] < 0.0 or values[-1] >= duration_s):
        raise ValueError("event times must lie in [0, duration_s)")
    if values.size > 1 and np.any(np.diff(values) <= 0.0):
        raise ValueError("event times must be strictly increasing")
    return values


def _r_squared(observed: npt.NDArray[np.float64], fitted: npt.NDArray[np.float64]) -> float:
    residual = float(np.sum((observed - fitted) ** 2))
    total = float(np.sum((observed - np.mean(observed)) ** 2))
    return 1.0 - residual / total if total > 0.0 else 1.0


def _jacobian_std(result: Any, parameter_index: int, scale: float) -> float:
    jacobian = np.asarray(result.jac, dtype=np.float64)
    degrees = max(1, jacobian.shape[0] - jacobian.shape[1])
    try:
        covariance = np.linalg.inv(jacobian.T @ jacobian) * (2.0 * float(result.cost) / degrees)
        log_std = float(np.sqrt(max(0.0, covariance[parameter_index, parameter_index])))
    except np.linalg.LinAlgError:
        return float("nan")
    return scale * log_std


def rossi_alpha(
    times_s: npt.ArrayLike,
    duration_s: float,
    *,
    maximum_lag_s: float = 0.008,
    bins: int = 80,
    alpha_bounds_per_s: tuple[float, float] = (100.0, 5_000.0),
) -> NoiseCurve:
    """Estimate Rossi-alpha from a binned forward pair-density curve."""
    times = _validate_times(times_s, duration_s)
    if times.size < 100 or bins < 12 or not 0.0 < maximum_lag_s < duration_s:
        raise ValueError("Rossi-alpha requires >=100 events, >=12 bins, and a valid lag")
    bin_width = maximum_lag_s / bins
    count_edges = np.arange(0.0, duration_s + bin_width, bin_width)
    counts, _ = np.histogram(times, bins=count_edges)
    lags = np.arange(1, bins + 1, dtype=np.float64)
    pair_counts = np.array(
        [np.dot(counts[:-offset], counts[offset:]) for offset in range(1, bins + 1)],
        dtype=np.float64,
    )
    lag_s = lags * bin_width
    exposure = np.maximum(duration_s - lag_s, bin_width) * bin_width
    density = pair_counts / exposure
    baseline0 = max(float(np.median(density[-max(8, bins // 5) :])), 1.0e-12)
    amplitude0 = max(float(density[0] - baseline0), baseline0 * 1.0e-6)
    lower_alpha, upper_alpha = alpha_bounds_per_s

    def residual(parameters: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        alpha, amplitude, baseline = np.exp(parameters)
        scale = np.sqrt(np.maximum(density, baseline0))
        return np.asarray(
            (rossi_model(lag_s, alpha, amplitude, baseline) - density) / scale,
            dtype=np.float64,
        )

    result = least_squares(
        residual,
        np.log([np.sqrt(lower_alpha * upper_alpha), amplitude0, baseline0]),
        bounds=(
            np.log([lower_alpha, baseline0 * 1.0e-10, baseline0 * 0.05]),
            np.log([upper_alpha, baseline0 * 100.0, baseline0 * 20.0]),
        ),
        max_nfev=2_000,
    )
    alpha, amplitude, baseline = np.exp(result.x)
    fitted = rossi_model(lag_s, alpha, amplitude, baseline)
    fit = AlphaFit(
        method="Rossi-alpha",
        alpha_per_s=float(alpha),
        alpha_std_per_s=float("nan"),
        naive_alpha_std_per_s=_jacobian_std(result, 0, float(alpha)),
        amplitude=float(amplitude),
        baseline=float(baseline),
        r_squared=_r_squared(density, fitted),
        bootstrap_alpha_per_s=np.empty(0, dtype=np.float64),
    )
    return NoiseCurve(lag_s, density, fitted, fit)


def feynman_alpha(
    times_s: npt.ArrayLike,
    duration_s: float,
    *,
    gate_widths_s: npt.ArrayLike | None = None,
    alpha_bounds_per_s: tuple[float, float] = (100.0, 5_000.0),
) -> NoiseCurve:
    """Estimate Feynman-alpha from non-overlapping count gates."""
    times = _validate_times(times_s, duration_s)
    if times.size < 100:
        raise ValueError("Feynman-alpha requires at least 100 events")
    if gate_widths_s is None:
        gate_widths_s = np.geomspace(2.0e-5, min(0.01, duration_s / 20.0), 32)
    gates = np.asarray(gate_widths_s, dtype=np.float64)
    if gates.ndim != 1 or gates.size < 8 or np.any(gates <= 0.0):
        raise ValueError("gate_widths_s must contain at least eight positive values")
    y_values = np.empty(gates.size, dtype=np.float64)
    for index, gate in enumerate(gates):
        gate_count = int(np.floor(duration_s / gate))
        if gate_count < 16:
            raise ValueError("each Feynman gate width requires at least sixteen gates")
        complete = times[times < gate_count * gate]
        event_bins = (complete / gate).astype(np.int64)
        counts = np.bincount(event_bins, minlength=gate_count)
        mean = float(np.mean(counts))
        y_values[index] = float(np.var(counts, ddof=1) / mean - 1.0)
    lower_alpha, upper_alpha = alpha_bounds_per_s
    y0 = max(float(np.median(y_values[-max(5, gates.size // 5) :])), 1.0e-6)
    scale = max(float(np.std(y_values)), y0 * 0.1, 1.0e-6)

    def residual(parameters: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        alpha, y_inf = np.exp(parameters)
        return (feynman_model(gates, alpha, y_inf) - y_values) / scale

    result = least_squares(
        residual,
        np.log([np.sqrt(lower_alpha * upper_alpha), y0]),
        bounds=(np.log([lower_alpha, 1.0e-10]), np.log([upper_alpha, 100.0])),
        max_nfev=2_000,
    )
    alpha, y_inf = np.exp(result.x)
    fitted = feynman_model(gates, alpha, y_inf)
    fit = AlphaFit(
        method="Feynman-alpha",
        alpha_per_s=float(alpha),
        alpha_std_per_s=float("nan"),
        naive_alpha_std_per_s=_jacobian_std(result, 0, float(alpha)),
        amplitude=float(y_inf),
        baseline=0.0,
        r_squared=_r_squared(y_values, fitted),
        bootstrap_alpha_per_s=np.empty(0, dtype=np.float64),
    )
    return NoiseCurve(gates, y_values, fitted, fit)


def _log_bin_spectrum(
    frequency_hz: npt.NDArray[np.float64], spectrum: npt.NDArray[np.float64], bins: int
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    positive = (frequency_hz > 0.0) & np.isfinite(spectrum) & (spectrum > 0.0)
    frequency = frequency_hz[positive]
    power = spectrum[positive]
    edges = np.geomspace(frequency[0], frequency[-1] * (1.0 + 1.0e-12), bins + 1)
    indices = np.digitize(frequency, edges) - 1
    x_values: list[float] = []
    y_values: list[float] = []
    for index in range(bins):
        selected = indices == index
        if np.any(selected):
            x_values.append(float(np.exp(np.mean(np.log(frequency[selected])))))
            y_values.append(float(np.exp(np.mean(np.log(power[selected])))))
    return np.asarray(x_values), np.asarray(y_values)


def psd_alpha(
    times_s: npt.ArrayLike,
    duration_s: float,
    *,
    count_bin_s: float = 5.0e-5,
    spectrum_bins: int = 100,
    alpha_bounds_per_s: tuple[float, float] = (100.0, 5_000.0),
) -> NoiseCurve:
    """Estimate Cohn-alpha from a Welch count spectrum and Lorentzian fit."""
    times = _validate_times(times_s, duration_s)
    sample_count = int(np.floor(duration_s / count_bin_s))
    if times.size < 100 or sample_count < 2_048:
        raise ValueError("PSD alpha requires >=100 events and >=2048 count bins")
    complete = times[times < sample_count * count_bin_s]
    event_bins = (complete / count_bin_s).astype(np.int64)
    counts = np.bincount(event_bins, minlength=sample_count).astype(np.float64)
    counts -= np.mean(counts)
    nperseg = min(16_384, max(2_048, 2 ** int(np.floor(np.log2(sample_count / 8)))))
    frequency, power = welch(
        counts,
        fs=1.0 / count_bin_s,
        window="hann",
        nperseg=nperseg,
        noverlap=nperseg // 2,
        detrend="constant",
        scaling="density",
    )
    frequency, power = _log_bin_spectrum(frequency, power, spectrum_bins)
    lower_alpha, upper_alpha = alpha_bounds_per_s
    high = max(float(np.median(power[-max(8, power.size // 5) :])), 1.0e-20)
    low = max(float(np.median(power[: max(5, power.size // 8)])), high)
    y0 = max(low / high - 1.0, 1.0e-4)

    def residual(parameters: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        alpha, y_inf, level = np.exp(parameters)
        return np.asarray(
            np.log(psd_model(frequency, alpha, y_inf, level)) - np.log(power),
            dtype=np.float64,
        )

    result = least_squares(
        residual,
        np.log([np.sqrt(lower_alpha * upper_alpha), y0, high]),
        bounds=(
            np.log([lower_alpha, 1.0e-8, high * 1.0e-3]),
            np.log([upper_alpha, 1.0e3, high * 1.0e3]),
        ),
        loss="soft_l1",
        max_nfev=3_000,
    )
    alpha, y_inf, level = np.exp(result.x)
    fitted = psd_model(frequency, alpha, y_inf, level)
    fit = AlphaFit(
        method="PSD",
        alpha_per_s=float(alpha),
        alpha_std_per_s=float("nan"),
        naive_alpha_std_per_s=_jacobian_std(result, 0, float(alpha)),
        amplitude=float(y_inf),
        baseline=float(level),
        r_squared=_r_squared(np.log(power), np.log(fitted)),
        bootstrap_alpha_per_s=np.empty(0, dtype=np.float64),
    )
    return NoiseCurve(frequency, power, fitted, fit)


def _block_bootstrap_times(
    times_s: npt.NDArray[np.float64],
    duration_s: float,
    block_count: int,
    rng: np.random.Generator,
) -> npt.NDArray[np.float64]:
    block_width = duration_s / block_count
    selected = rng.integers(0, block_count, size=block_count)
    pieces: list[npt.NDArray[np.float64]] = []
    for output_index, source_index in enumerate(selected):
        start = source_index * block_width
        stop = start + block_width
        left = int(np.searchsorted(times_s, start, side="left"))
        right = int(np.searchsorted(times_s, stop, side="left"))
        pieces.append(times_s[left:right] - start + output_index * block_width)
    values = np.concatenate(pieces) if pieces else np.empty(0, dtype=np.float64)
    # Exact ties can arise when a block is repeated; jitter only by machine epsilon.
    if values.size > 1:
        values = np.sort(values)
        duplicate = np.diff(values) <= 0.0
        if np.any(duplicate):
            values += np.arange(values.size) * np.finfo(np.float64).eps * duration_s
    return values[values < duration_s]


def _with_bootstrap(curve: NoiseCurve, samples: list[float]) -> NoiseCurve:
    values = np.asarray(samples, dtype=np.float64)
    values = values[np.isfinite(values)]
    bootstrap_std = float(np.std(values, ddof=1)) if values.size > 1 else float("nan")
    naive = curve.fit.naive_alpha_std_per_s
    if np.isfinite(naive):
        corrected = max(bootstrap_std, naive * 1.05)
    else:
        corrected = bootstrap_std
    return replace(
        curve,
        fit=replace(
            curve.fit,
            alpha_std_per_s=corrected,
            bootstrap_alpha_per_s=values,
        ),
    )


def analyze_event_noise(
    times_s: npt.ArrayLike,
    duration_s: float,
    *,
    bootstrap_replicates: int = 24,
    bootstrap_blocks: int = 32,
    seed: int = 0,
    maximum_lag_s: float = 0.008,
    alpha_bounds_per_s: tuple[float, float] = (100.0, 5_000.0),
) -> NoiseAnalysis:
    """Run all three estimators and a common time-block bootstrap."""
    times = _validate_times(times_s, duration_s)
    if bootstrap_replicates < 0 or bootstrap_blocks < 8:
        raise ValueError("bootstrap_replicates must be non-negative and blocks >= 8")
    rossi = rossi_alpha(
        times,
        duration_s,
        maximum_lag_s=maximum_lag_s,
        alpha_bounds_per_s=alpha_bounds_per_s,
    )
    feynman = feynman_alpha(times, duration_s, alpha_bounds_per_s=alpha_bounds_per_s)
    psd = psd_alpha(times, duration_s, alpha_bounds_per_s=alpha_bounds_per_s)
    bootstrap: dict[MethodName, list[float]] = {
        "Rossi-alpha": [],
        "Feynman-alpha": [],
        "PSD": [],
    }
    rng = np.random.default_rng(seed)
    for _ in range(bootstrap_replicates):
        sampled = _block_bootstrap_times(times, duration_s, bootstrap_blocks, rng)
        if sampled.size < 100:
            continue
        try:
            curve = rossi_alpha(
                sampled,
                duration_s,
                maximum_lag_s=maximum_lag_s,
                alpha_bounds_per_s=alpha_bounds_per_s,
            )
            bootstrap["Rossi-alpha"].append(curve.fit.alpha_per_s)
        except (ValueError, RuntimeError):
            pass
        try:
            curve = feynman_alpha(sampled, duration_s, alpha_bounds_per_s=alpha_bounds_per_s)
            bootstrap["Feynman-alpha"].append(curve.fit.alpha_per_s)
        except (ValueError, RuntimeError):
            pass
        try:
            curve = psd_alpha(sampled, duration_s, alpha_bounds_per_s=alpha_bounds_per_s)
            bootstrap["PSD"].append(curve.fit.alpha_per_s)
        except (ValueError, RuntimeError):
            pass
    return NoiseAnalysis(
        rossi=_with_bootstrap(rossi, bootstrap["Rossi-alpha"]),
        feynman=_with_bootstrap(feynman, bootstrap["Feynman-alpha"]),
        psd=_with_bootstrap(psd, bootstrap["PSD"]),
        duration_s=duration_s,
        event_count=int(times.size),
        observed_rate_cps=float(times.size / duration_s),
    )


def hazama_vtm_correction(
    observed_y: npt.ArrayLike, observed_rate_cps: float, dead_time_s: float
) -> npt.NDArray[np.float64]:
    """Apply the first-order non-extending-dead-time VTM lift ``Y + 2 R d``.

    This is the practical weak-loss Hazama/Mueller correction.  It corrects the
    dead-time intercept before fitting the pure-prompt Feynman curve.
    """
    values = np.asarray(observed_y, dtype=np.float64)
    if observed_rate_cps < 0.0 or dead_time_s < 0.0:
        raise ValueError("observed rate and dead time must be non-negative")
    return values + 2.0 * observed_rate_cps * dead_time_s


def refit_feynman_curve(
    gate_widths_s: npt.ArrayLike,
    y_values: npt.ArrayLike,
    *,
    alpha_bounds_per_s: tuple[float, float] = (100.0, 5_000.0),
) -> NoiseCurve:
    """Fit precomputed Feynman-Y values, including corrected curves."""
    gates = np.asarray(gate_widths_s, dtype=np.float64)
    values = np.asarray(y_values, dtype=np.float64)
    if gates.shape != values.shape or gates.ndim != 1 or gates.size < 8:
        raise ValueError("gate widths and Y values must be aligned one-dimensional arrays")
    lower_alpha, upper_alpha = alpha_bounds_per_s
    y0 = max(float(np.median(values[-max(5, values.size // 5) :])), 1.0e-6)
    scale = max(float(np.std(values)), y0 * 0.1, 1.0e-6)

    def residual(parameters: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        alpha, y_inf = np.exp(parameters)
        return (feynman_model(gates, alpha, y_inf) - values) / scale

    result = least_squares(
        residual,
        np.log([np.sqrt(lower_alpha * upper_alpha), y0]),
        bounds=(np.log([lower_alpha, 1.0e-10]), np.log([upper_alpha, 100.0])),
    )
    alpha, y_inf = np.exp(result.x)
    fitted = feynman_model(gates, alpha, y_inf)
    fit = AlphaFit(
        method="Feynman-alpha",
        alpha_per_s=float(alpha),
        alpha_std_per_s=float("nan"),
        naive_alpha_std_per_s=_jacobian_std(result, 0, float(alpha)),
        amplitude=float(y_inf),
        baseline=0.0,
        r_squared=_r_squared(values, fitted),
        bootstrap_alpha_per_s=np.empty(0, dtype=np.float64),
    )
    return NoiseCurve(gates, values, fitted, fit)
