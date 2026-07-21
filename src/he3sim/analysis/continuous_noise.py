"""Continuous-signal neutron-noise estimators for Phase C.

This module operates directly on continuous voltage waveforms (rather than
pulse-mode event times) and implements the three core methods described in
ROADMAP_v2 §8: continuous ACF/VTM with alpha_e terms, Wiener deconvolution,
and dual-detector CCF/CTM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
from scipy.fft import fft, ifft  # type: ignore[import-untyped]
from scipy.optimize import least_squares  # type: ignore[import-untyped]

from he3sim.analysis.noise import AlphaFit
from he3sim.physics.pulse_models import (
    normalized_double_exponential,
)

ALPHA_BOUNDS_PER_S: tuple[float, float] = (100.0, 5_000.0)


@dataclass(frozen=True, slots=True)
class ContinuousACFFit:
    r"""Fit result for the continuous ACF model.

    The fitted model is
    ``phi*exp(-alpha*|theta|) + psi1*exp(-alpha_e*|theta|)
    + psi2*|theta|*exp(-alpha_e*|theta|)``
    where *alpha_e* is the detector pulse decay constant (~1/tau_d).
    """

    alpha_per_s: float
    alpha_std_per_s: float
    alpha_e_per_s: float
    phi: float
    psi1: float
    psi2: float
    r_squared: float


@dataclass(frozen=True, slots=True)
class ContinuousVTMCurve:
    """VTM computed from continuous waveform over a set of gate widths."""

    gate_widths_s: npt.NDArray[np.float64]
    vtm_values: npt.NDArray[np.float64]
    fitted: npt.NDArray[np.float64]
    fit: AlphaFit


@dataclass(frozen=True, slots=True)
class DeconvolutionResult:
    """Result of Wiener / inverse-Fourier pulse deconvolution."""

    deconvolved: npt.NDArray[np.float64]
    gamma: float
    nsr_used: float
    pulse_kernel_energy: float
    residual_ratio: float


@dataclass(frozen=True, slots=True)
class ContinuousNoiseAnalysis:
    """Union of continuous ACF, VTM, and deconvolution results."""

    acf_lags_s: npt.NDArray[np.float64]
    acf_values: npt.NDArray[np.float64]
    acf_fit: ContinuousACFFit
    vtm: ContinuousVTMCurve
    deconv_result: DeconvolutionResult
    alpha_true_per_s: float
    duration_s: float
    sample_rate_hz: float
    event_count: int


def _r_squared(observed: npt.NDArray[np.float64], fitted: npt.NDArray[np.float64]) -> float:
    residual = float(np.sum((observed - fitted) ** 2))
    total = float(np.sum((observed - np.mean(observed)) ** 2))
    return 1.0 - residual / total if total > 0.0 else 1.0


# ------------------------------------------------------------------ ACF / VTM


def _acf_model(
    lags_s: npt.ArrayLike,
    alpha_per_s: float,
    alpha_e_per_s: float,
    phi: float,
    psi1: float,
    psi2: float,
) -> npt.NDArray[np.float64]:
    """Evaluate the five-parameter continuous ACF model."""
    lag = np.asarray(lags_s, dtype=np.float64)
    abs_lag = np.abs(lag)
    term1 = phi * np.exp(-alpha_per_s * abs_lag)
    term2 = psi1 * np.exp(-alpha_e_per_s * abs_lag)
    term3 = psi2 * abs_lag * np.exp(-alpha_e_per_s * abs_lag)
    return np.asarray(term1 + term2 + term3, dtype=np.float64)


def compute_acf(
    voltage: npt.ArrayLike,
    sample_rate_hz: float,
    max_lag_s: float = 0.02,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Compute the continuous-voltage autocovariance function via FFT."""
    signal = np.asarray(voltage, dtype=np.float64)
    if signal.ndim != 1 or signal.size < 100:
        raise ValueError("voltage must be a one-dimensional array with at least 100 samples")
    signal = signal - np.mean(signal)
    n = signal.size
    n_fft = 1
    while n_fft < 2 * n - 1:
        n_fft <<= 1
    signal_fft = fft(signal, n_fft)
    acf_full = np.real(ifft(signal_fft * np.conj(signal_fft)))
    acf_full = acf_full[:n]
    acf_full /= np.arange(n, 0, -1, dtype=np.float64)
    norm = acf_full[0] if acf_full[0] != 0.0 else 1.0
    acf_full /= norm
    max_lag_index = min(int(np.ceil(max_lag_s * sample_rate_hz)), n - 1)
    lags_s = np.arange(max_lag_index + 1, dtype=np.float64) / sample_rate_hz
    acf_values = acf_full[: max_lag_index + 1]
    mask = lags_s > 0.0
    return lags_s[mask], acf_values[mask]


def _f1(x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """VTM shape function f1(x) = 1 - (1-exp(-x))/x."""
    result = np.zeros_like(x)
    small = np.abs(x) < 1.0e-8
    result[small] = x[small] / 2.0 - x[small] ** 2 / 6.0
    result[~small] = 1.0 - (-np.expm1(-x[~small])) / x[~small]
    return np.asarray(result, dtype=np.float64)


def _f2(x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """VTM shape function f2(x) = 1 + e^{-x} - 2(1-e^{-x})/x."""
    result = np.zeros_like(x)
    small = np.abs(x) < 1.0e-8
    exp_neg = np.exp(-x[~small])
    result[small] = x[small] ** 2 / 6.0
    result[~small] = 1.0 + exp_neg - 2.0 * (1.0 - exp_neg) / x[~small]
    return np.asarray(result, dtype=np.float64)


def _vtm_model(
    gate_width_s: npt.ArrayLike,
    alpha_per_s: float,
    alpha_e_per_s: float,
    capital_phi: float,
    capital_psi1: float,
    capital_psi2: float,
) -> npt.NDArray[np.float64]:
    """Evaluate the five-parameter continuous VTM model."""
    gate = np.asarray(gate_width_s, dtype=np.float64)
    alpha_gate = alpha_per_s * gate
    alpha_e_gate = alpha_e_per_s * gate
    return np.asarray(
        capital_phi * _f1(alpha_gate)
        + capital_psi1 * _f1(alpha_e_gate)
        + capital_psi2 * _f2(alpha_e_gate),
        dtype=np.float64,
    )


def compute_vtm_waveform(
    voltage: npt.ArrayLike,
    sample_rate_hz: float,
    gate_widths_s: npt.ArrayLike | None = None,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Compute variance-to-mean ratio from continuous voltage over gate widths."""
    signal = np.asarray(voltage, dtype=np.float64)
    if signal.ndim != 1 or signal.size < 100:
        raise ValueError("voltage must be a one-dimensional array with at least 100 samples")
    signal = signal - np.mean(signal)
    duration_s = signal.size / sample_rate_hz
    if gate_widths_s is None:
        gate_widths_s = np.geomspace(1.0e-5, duration_s / 20.0, 32)
    gates = np.asarray(gate_widths_s, dtype=np.float64)
    if gates.ndim != 1 or gates.size < 8 or np.any(gates <= 0.0):
        raise ValueError("gate_widths_s must contain at least eight positive values")
    vtm_values = np.empty(gates.size, dtype=np.float64)
    for index, gate in enumerate(gates):
        gate_samples = max(1, int(np.floor(gate * sample_rate_hz)))
        gate_count = signal.size // gate_samples
        if gate_count < 16:
            raise ValueError(
                f"VTM gate width {gate:.3g}s gives only {gate_count} gates "
                f"(need >=16); use shorter gate widths or a longer signal"
            )
        trimmed = gate_count * gate_samples
        segment = signal[:trimmed].reshape(gate_count, gate_samples)
        gate_means = np.mean(segment, axis=1)
        variance = float(np.var(gate_means, ddof=1))
        mean_val = float(np.mean(gate_means))
        vtm_values[index] = variance / max(mean_val**2, 1.0e-20)
    return gates, vtm_values


def fit_continuous_acf(
    lags_s: npt.ArrayLike,
    acf_values: npt.ArrayLike,
    alpha_e_guess_per_s: float,
    alpha_bounds_per_s: tuple[float, float] = ALPHA_BOUNDS_PER_S,
    *,
    min_lag_s: float = 0.0002,
) -> ContinuousACFFit:
    """Fit the continuous ACF model, ignoring short lags dominated by alpha_e.

    Only lags >= ``min_lag_s`` are used for fitting, which removes the fast
    pulse-self-correlation regime (~1/tau_d).  A simpler two-parameter
    ``phi*exp(-alpha*|theta|)`` model is fitted on the truncated data for
    numerical stability.
    """
    lags = np.asarray(lags_s, dtype=np.float64)
    values = np.asarray(acf_values, dtype=np.float64)
    if lags.shape != values.shape or lags.ndim != 1 or lags.size < 8:
        raise ValueError("lags and ACF values must be aligned one-dimensional arrays")
    mask = lags >= min_lag_s
    if not np.any(mask):
        raise ValueError("no ACF points beyond min_lag_s; increase max_lag_s or reduce min_lag_s")
    lags_trunc = lags[mask]
    values_trunc = values[mask]
    if lags_trunc.size < 4:
        raise ValueError("too few ACF points for fitting after min_lag_s truncation")
    lower_alpha, upper_alpha = alpha_bounds_per_s
    baseline_val = max(float(np.median(values_trunc[-max(3, values_trunc.size // 4) :])), 1.0e-12)
    amplitude0 = max(float(values_trunc[0]) - baseline_val, 1.0e-12)
    alpha_guess = np.sqrt(lower_alpha * upper_alpha)
    scale = max(float(np.std(values_trunc)), 1.0e-12)

    def residual(params: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        alpha, amplitude, baseline = np.exp(params)
        model_vals = baseline + amplitude * np.exp(-alpha * lags_trunc)
        return np.asarray((model_vals - values_trunc) / scale, dtype=np.float64)

    result = least_squares(
        residual,
        np.log([alpha_guess, amplitude0, baseline_val]),
        bounds=(
            np.log([lower_alpha, 1.0e-15, 1.0e-15]),
            np.log([upper_alpha, 1e3, 1e3]),
        ),
        max_nfev=2_000,
    )
    alpha, amplitude, baseline = np.exp(result.x)
    return ContinuousACFFit(
        alpha_per_s=float(alpha),
        alpha_std_per_s=float("nan"),
        alpha_e_per_s=alpha_e_guess_per_s,
        phi=float(amplitude),
        psi1=0.0,
        psi2=0.0,
        r_squared=_r_squared(values_trunc, baseline + amplitude * np.exp(-alpha * lags_trunc)),
    )


def fit_continuous_vtm(
    gate_widths_s: npt.ArrayLike,
    vtm_values: npt.ArrayLike,
    alpha_e_guess_per_s: float,
    alpha_bounds_per_s: tuple[float, float] = ALPHA_BOUNDS_PER_S,
    *,
    min_gate_s: float = 0.0002,
) -> ContinuousVTMCurve:
    """Fit VTM on gates >= ``min_gate_s`` where alpha_e terms have saturated.

    For gates much longer than the pulse decay time, the alpha_e contributions
    are constant offsets and the shape is dominated by f1(alpha*T).
    """
    gates = np.asarray(gate_widths_s, dtype=np.float64)
    values = np.asarray(vtm_values, dtype=np.float64)
    if gates.shape != values.shape or gates.ndim != 1 or gates.size < 8:
        raise ValueError("gates and VTM values must be aligned one-dimensional arrays")
    mask = gates >= min_gate_s
    if not np.any(mask) or np.sum(mask) < 4:
        mask = np.ones(gates.size, dtype=bool)
    gates_trunc = gates[mask]
    values_trunc = values[mask]
    lower_alpha, upper_alpha = alpha_bounds_per_s
    plateau = max(float(np.median(values_trunc[-max(3, values_trunc.size // 4) :])), 1.0e-12)
    y0 = float(np.clip(plateau, 1.0e-15, 5e5))
    alpha_guess = np.sqrt(lower_alpha * upper_alpha)
    scale = max(float(np.std(values_trunc)), plateau * 0.05, 1.0e-12)

    def residual(params: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        alpha, y_inf = np.exp(params)
        return np.asarray(
            (y_inf * _f1(alpha * gates_trunc) - values_trunc) / scale,
            dtype=np.float64,
        )

    result = least_squares(
        residual,
        np.log([alpha_guess, y0]),
        bounds=(
            np.log([lower_alpha, 1.0e-15]),
            np.log([upper_alpha, 1e6]),
        ),
        max_nfev=2_000,
    )
    alpha, y_inf = np.exp(result.x)
    fitted = y_inf * _f1(alpha * gates)
    alpha_std = float("nan")
    try:
        jac = np.asarray(result.jac, dtype=np.float64)
        degrees = max(1, jac.shape[0] - jac.shape[1])
        cov = np.linalg.inv(jac.T @ jac) * (2.0 * float(result.cost) / degrees)
        alpha_std = float(np.sqrt(max(0.0, cov[0, 0]))) * float(alpha)
    except np.linalg.LinAlgError:
        pass
    fit = AlphaFit(
        method="Continuous-VTM",
        alpha_per_s=float(alpha),
        alpha_std_per_s=alpha_std,
        naive_alpha_std_per_s=alpha_std,
        amplitude=float(y_inf),
        baseline=0.0,
        r_squared=_r_squared(values_trunc, y_inf * _f1(alpha * gates_trunc)),
        bootstrap_alpha_per_s=np.empty(0, dtype=np.float64),
    )
    return ContinuousVTMCurve(gates, values, fitted, fit)


# --------------------------------------------------------------- Deconvolution


def pulse_kernel_samples(
    sample_rate_hz: float,
    tau_r_s: float,
    tau_d_s: float,
    kernel_duration_s: float | None = None,
) -> npt.NDArray[np.float64]:
    """Return a time-domain pulse kernel array suitable for deconvolution."""
    if kernel_duration_s is None:
        kernel_duration_s = 8.0 * tau_d_s
    sample_count = int(np.ceil(kernel_duration_s * sample_rate_hz))
    times = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    kernel = normalized_double_exponential(times, tau_r_s, tau_d_s)
    if not isinstance(kernel, np.ndarray):
        raise RuntimeError("normalized_double_exponential did not return an array")
    return np.asarray(kernel, dtype=np.float64)


def wiener_deconvolution(
    waveform: npt.ArrayLike,
    pulse_kernel: npt.ArrayLike,
    gamma: float = 0.01,
    nsr: float = 0.01,
) -> DeconvolutionResult:
    """Apply Wiener deconvolution to a continuous voltage waveform.

    Parameters
    ----------
    waveform : array-like
        Continuous time-domain signal to deconvolve.
    pulse_kernel : array-like
        The known (averaged) unit pulse shape.
    gamma : float
        Wiener regularisation strength (0 = pure inverse filter).
    nsr : float
        Estimated noise-to-signal power ratio for the Wiener denominator.
    """
    signal = np.asarray(waveform, dtype=np.float64)
    kernel = np.asarray(pulse_kernel, dtype=np.float64)
    if signal.ndim != 1 or kernel.ndim != 1:
        raise ValueError("waveform and kernel must be one-dimensional")
    if signal.size < kernel.size:
        raise ValueError("waveform must be longer than the pulse kernel")
    n_total = signal.size + kernel.size - 1
    n_fft = 1
    while n_fft < n_total:
        n_fft <<= 1
    signal_fft = fft(signal, n_fft)
    kernel_fft = fft(kernel, n_fft)
    kernel_power = np.abs(kernel_fft) ** 2
    wiener = np.conj(kernel_fft) / (kernel_power + gamma * nsr)
    result_fft = signal_fft * wiener
    deconvolved_raw = np.real(ifft(result_fft))
    deconvolved = deconvolved_raw[: signal.size].copy()
    recon_signal = np.real(ifft(fft(deconvolved, n_fft) * kernel_fft))
    recon_signal = recon_signal[: signal.size]
    residual = np.sum((signal - recon_signal) ** 2) / max(np.sum(signal**2), 1.0e-20)
    return DeconvolutionResult(
        deconvolved=deconvolved,
        gamma=gamma,
        nsr_used=nsr,
        pulse_kernel_energy=float(np.sum(kernel**2)),
        residual_ratio=float(residual),
    )


def threshold_deconvolved(
    deconvolved: npt.ArrayLike,
    threshold: float,
) -> npt.NDArray[np.float64]:
    """Zero entries of a deconvolved signal below a magnitude threshold."""
    values = np.asarray(deconvolved, dtype=np.float64)
    result = values.copy()
    result[np.abs(result) < threshold] = 0.0
    return result


def scan_gamma_nsr(
    waveform: npt.ArrayLike,
    pulse_kernel: npt.ArrayLike,
    gamma_values: npt.ArrayLike | None = None,
    nsr_values: npt.ArrayLike | None = None,
) -> dict[str, Any]:
    """Scan the gamma-NSR stability domain for Wiener deconvolution.

    Returns a dictionary with 'gamma_grid', 'nsr_grid', and 'residual_map'.
    """
    signal = np.asarray(waveform, dtype=np.float64)
    if gamma_values is None:
        gamma_values = np.logspace(-4, 2, 13)
    if nsr_values is None:
        nsr_values = np.logspace(-4, 0, 9)
    gammas = np.asarray(gamma_values, dtype=np.float64)
    nsrs = np.asarray(nsr_values, dtype=np.float64)
    residual_map = np.empty((gammas.size, nsrs.size), dtype=np.float64)
    for gi, gamma in enumerate(gammas):
        for ni, nsr in enumerate(nsrs):
            try:
                result = wiener_deconvolution(
                    signal, pulse_kernel, gamma=float(gamma), nsr=float(nsr)
                )
                residual_map[gi, ni] = result.residual_ratio
            except (ValueError, RuntimeError):
                residual_map[gi, ni] = float("nan")
    return {
        "gamma_grid": gammas,
        "nsr_grid": nsrs,
        "residual_map": residual_map,
    }


# ---------------------------------------------------- Dual-detector CCF / CTM


def compute_ccf(
    voltage_ch1: npt.ArrayLike,
    voltage_ch2: npt.ArrayLike,
    max_lag_s: float,
    sample_rate_hz: float,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Compute cross-covariance between two voltage channels via FFT."""
    ch1 = np.asarray(voltage_ch1, dtype=np.float64)
    ch2 = np.asarray(voltage_ch2, dtype=np.float64)
    if ch1.shape != ch2.shape or ch1.ndim != 1:
        raise ValueError("channel arrays must have the same one-dimensional shape")
    if ch1.size < 100:
        raise ValueError("each channel requires at least 100 samples")
    ch1 = ch1 - np.mean(ch1)
    ch2 = ch2 - np.mean(ch2)
    n = ch1.size
    n_fft = 1
    while n_fft < 2 * n - 1:
        n_fft <<= 1
    f1 = fft(ch1, n_fft)
    f2 = fft(ch2, n_fft)
    cross_full = np.real(ifft(f1 * np.conj(f2)))
    cross_full = cross_full[:n]
    cross_full /= np.arange(n, 0, -1, dtype=np.float64)
    variance_ch1 = float(np.var(ch1))
    variance_ch2 = float(np.var(ch2))
    if variance_ch1 > 0.0 and variance_ch2 > 0.0:
        cross_full = cross_full / np.sqrt(variance_ch1 * variance_ch2)
    max_index = min(int(np.ceil(max_lag_s * sample_rate_hz)), n - 1)
    lags_s = np.arange(max_index + 1, dtype=np.float64) / sample_rate_hz
    return lags_s, cross_full[: max_index + 1]


def compute_ctm(
    voltage_ch1: npt.ArrayLike,
    voltage_ch2: npt.ArrayLike,
    sample_rate_hz: float,
    gate_widths_s: npt.ArrayLike | None = None,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Compute cross-covariance-to-mean ratio for dual-detector gate counts."""
    ch1 = np.asarray(voltage_ch1, dtype=np.float64)
    ch2 = np.asarray(voltage_ch2, dtype=np.float64)
    if ch1.shape != ch2.shape or ch1.ndim != 1:
        raise ValueError("channel arrays must have the same one-dimensional shape")
    duration_s = ch1.size / sample_rate_hz
    if gate_widths_s is None:
        gate_widths_s = np.geomspace(1.0e-5, duration_s / 20.0, 32)
    gates = np.asarray(gate_widths_s, dtype=np.float64)
    if gates.ndim != 1 or gates.size < 8:
        raise ValueError("gate_widths_s must contain at least eight positive values")
    ctm_values = np.empty(gates.size, dtype=np.float64)
    for index, gate in enumerate(gates):
        gate_samples = max(1, int(np.floor(gate * sample_rate_hz)))
        gate_count = ch1.size // gate_samples
        if gate_count < 16:
            raise ValueError(
                f"CTM gate width {gate:.3g}s gives only {gate_count} gates "
                f"(need >=16); use shorter gate widths or a longer signal"
            )
        trimmed = gate_count * gate_samples
        seg1 = ch1[:trimmed].reshape(gate_count, gate_samples)
        seg2 = ch2[:trimmed].reshape(gate_count, gate_samples)
        means1 = np.mean(seg1, axis=1)
        means2 = np.mean(seg2, axis=1)
        covariance = float(np.cov(means1, means2, ddof=1)[0, 1])
        mean1 = float(np.mean(means1))
        mean2 = float(np.mean(means2))
        denominator = max(abs(mean1 * mean2), 1.0e-20)
        ctm_values[index] = covariance / denominator
    return gates, ctm_values


# ----------------------------------------------------------- Orchestration


def analyze_continuous_noise(
    voltage: npt.ArrayLike,
    sample_rate_hz: float,
    tau_r_s: float,
    tau_d_s: float,
    alpha_true_per_s: float,
    *,
    max_lag_s: float = 0.02,
    alpha_bounds_per_s: tuple[float, float] = ALPHA_BOUNDS_PER_S,
    deconv_gamma: float = 0.01,
    deconv_nsr: float = 0.01,
    gate_widths_s: npt.ArrayLike | None = None,
) -> ContinuousNoiseAnalysis:
    """Run continuous ACF, VTM, and Wiener deconvolution on a single waveform."""
    signal = np.asarray(voltage, dtype=np.float64)
    if signal.ndim != 1:
        raise ValueError("voltage must be a one-dimensional array")
    duration_s = signal.size / sample_rate_hz

    alpha_e_guess = 1.0 / tau_d_s
    lags_s, acf_values = compute_acf(signal, sample_rate_hz, max_lag_s=max_lag_s)
    acf_fit = fit_continuous_acf(lags_s, acf_values, alpha_e_guess, alpha_bounds_per_s)

    gws, vtm_values = compute_vtm_waveform(signal, sample_rate_hz, gate_widths_s)
    vtm_curve = fit_continuous_vtm(gws, vtm_values, alpha_e_guess, alpha_bounds_per_s)

    kernel = pulse_kernel_samples(sample_rate_hz, tau_r_s, tau_d_s)
    deconv_result = wiener_deconvolution(signal, kernel, gamma=deconv_gamma, nsr=deconv_nsr)

    return ContinuousNoiseAnalysis(
        acf_lags_s=lags_s,
        acf_values=acf_values,
        acf_fit=acf_fit,
        vtm=vtm_curve,
        deconv_result=deconv_result,
        alpha_true_per_s=alpha_true_per_s,
        duration_s=duration_s,
        sample_rate_hz=sample_rate_hz,
        event_count=0,
    )
