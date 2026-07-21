"""Unit tests for continuous-signal noise estimators."""

from __future__ import annotations

import numpy as np
import pytest

from he3sim.analysis.continuous_noise import (
    _acf_model,
    _f1,
    _f2,
    _vtm_model,
    compute_acf,
    compute_ccf,
    compute_ctm,
    compute_vtm_waveform,
    fit_continuous_acf,
    fit_continuous_vtm,
    pulse_kernel_samples,
)


class TestShapeFunctions:
    def test_f1_zero_limit(self) -> None:
        x = np.array([1.0e-10, 1.0e-9], dtype=np.float64)
        result = _f1(x)
        assert np.all(np.isfinite(result))
        assert float(result[0]) == pytest.approx(0.0, abs=1.0e-10)

    def test_f1_large_argument(self) -> None:
        x = np.array([10.0, 100.0], dtype=np.float64)
        result = _f1(x)
        assert np.all(result > 0.9)

    def test_f2_zero_limit(self) -> None:
        x = np.array([1.0e-10, 1.0e-9], dtype=np.float64)
        result = _f2(x)
        assert np.all(np.isfinite(result))
        assert float(result[0]) == pytest.approx(0.0, abs=1.0e-10)

    def test_f1_f2_positive(self) -> None:
        x = np.logspace(-4, 2, 50)
        assert np.all(_f1(x) >= 0.0)
        assert np.all(_f2(x) >= 0.0)


class TestACFModel:
    def test_acf_model_positive_params(self) -> None:
        lags = np.linspace(0.0, 0.01, 100)
        result = _acf_model(lags, 1_000.0, 100_000.0, 1.0, 0.1, 0.01)
        assert result.shape == lags.shape
        assert np.all(np.isfinite(result))
        assert float(result[0]) > 0.0

    def test_acf_model_decays_to_zero(self) -> None:
        lags = np.linspace(0.0, 0.05, 500)
        result = _acf_model(lags, 500.0, 50_000.0, 0.5, 0.1, 0.01)
        assert float(result[-1]) < float(result[0]) * 0.1


class TestVTMCompute:
    def test_vtm_returns_positive(self) -> None:
        rng = np.random.default_rng(42)
        voltage = rng.normal(0.0, 0.01, 200_000).astype(np.float64)
        gates, vtm = compute_vtm_waveform(
            voltage, 1.0e6, gate_widths_s=np.geomspace(1e-5, 0.002, 20)
        )
        assert gates.size > 8
        assert np.all(vtm >= 0.0)

    def test_vtm_rejects_short_signal(self) -> None:
        with pytest.raises(ValueError):
            compute_vtm_waveform(np.array([0.0, 1.0]), 1.0e6)


class TestACFCompute:
    def test_acf_white_noise_decays(self) -> None:
        rng = np.random.default_rng(99)
        voltage = rng.normal(0.0, 0.01, 50_000).astype(np.float64)
        lags, acf = compute_acf(voltage, 1.0e6, max_lag_s=0.005)
        assert lags.size > 10
        assert np.all(np.isfinite(acf))
        assert float(np.abs(acf[-1])) < 0.2

    def test_acf_rejects_short_signal(self) -> None:
        with pytest.raises(ValueError):
            compute_acf(np.array([0.0]), 1.0e6)


class TestACFFitting:
    def test_fit_continuous_acf_recovers_params(self) -> None:
        rng = np.random.default_rng(2025)
        lags = np.linspace(1.0e-5, 0.008, 120)
        true_acf = _acf_model(lags, 1_000.0, 100_000.0, 0.5, 0.1, 0.01)
        noisy = true_acf + rng.normal(0.0, 1.0e-4, lags.size)
        fit = fit_continuous_acf(lags, noisy, 100_000.0)
        assert fit.r_squared > 0.9
        assert fit.alpha_per_s == pytest.approx(1_000.0, rel=0.5)


class TestCCFCTM:
    def test_ccf_identical_channels(self) -> None:
        rng = np.random.default_rng(77)
        voltage = rng.normal(0.0, 0.01, 10_000).astype(np.float64)
        lags, ccf = compute_ccf(voltage, voltage, 0.005, 1.0e6)
        assert lags.size > 5
        assert float(ccf[0]) == pytest.approx(1.0, abs=0.1)

    def test_ctm_positive_values(self) -> None:
        rng = np.random.default_rng(88)
        v1 = rng.normal(0.0, 0.01, 200_000).astype(np.float64)
        v2 = rng.normal(0.0, 0.01, 200_000).astype(np.float64)
        gates, ctm = compute_ctm(v1, v2, 1.0e6, gate_widths_s=np.geomspace(1e-5, 0.002, 20))
        assert gates.size > 8

    def test_ccf_rejects_mismatched_arrays(self) -> None:
        with pytest.raises(ValueError):
            compute_ccf(np.zeros(10), np.zeros(20), 0.001, 1.0e6)


class TestPulseKernel:
    def test_kernel_normalization(self) -> None:
        kernel = pulse_kernel_samples(1.0e8, 1.0e-6, 1.0e-5)
        assert kernel.size > 10
        peak = float(np.max(kernel))
        assert peak == pytest.approx(1.0, abs=0.02)

    def test_kernel_positive_and_causal(self) -> None:
        kernel = pulse_kernel_samples(1.0e8, 1.0e-6, 5.0e-6)
        assert float(kernel[0]) >= 0.0
        assert np.all(kernel >= -1.0e-15)


class TestVTMContinuousFitting:
    def test_fit_continuous_vtm_constrained(self) -> None:
        rng = np.random.default_rng(1234)
        gates = np.geomspace(1.0e-5, 0.002, 24)
        true_vtm = _vtm_model(gates, 1_000.0, 100_000.0, 0.02, 0.005, 0.001)
        noisy = true_vtm + rng.normal(0.0, 1.0e-5, gates.size)
        curve = fit_continuous_vtm(gates, noisy, 100_000.0)
        assert curve.fit.r_squared > 0.9
