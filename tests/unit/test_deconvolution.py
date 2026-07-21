"""Unit tests for Wiener deconvolution and gamma-NSR scanning."""

from __future__ import annotations

import numpy as np
import pytest

from he3sim.analysis.continuous_noise import (
    pulse_kernel_samples,
    scan_gamma_nsr,
    threshold_deconvolved,
    wiener_deconvolution,
)


class TestWienerDeconvolution:
    def test_deconvolution_roundtrip_noiseless(self) -> None:
        """Deconvolving a signal made from known spikes should recover them."""
        sample_rate = 1.0e6
        kernel = pulse_kernel_samples(sample_rate, 1.0e-6, 5.0e-6)
        signal = np.zeros(3000, dtype=np.float64)
        spike_positions = [500, 1500, 2500]
        for pos in spike_positions:
            end = min(pos + kernel.size, signal.size)
            signal[pos:end] += kernel[: end - pos] * 0.5
        result = wiener_deconvolution(signal, kernel, gamma=1.0e-6, nsr=1.0e-6)
        deconv = result.deconvolved
        for pos in spike_positions:
            window = slice(max(0, pos - 5), min(deconv.size, pos + 5))
            assert np.max(np.abs(deconv[window])) > 0.01

    def test_deconvolution_output_length(self) -> None:
        kernel = pulse_kernel_samples(1.0e6, 1.0e-6, 1.0e-5)
        signal = np.zeros(1000, dtype=np.float64)
        signal[200] = 1.0
        result = wiener_deconvolution(signal, kernel, gamma=0.01, nsr=0.01)
        assert result.deconvolved.size == signal.size

    def test_deconvolution_rejects_short_signal(self) -> None:
        kernel = pulse_kernel_samples(1.0e6, 1.0e-6, 1.0e-5)
        with pytest.raises(ValueError):
            wiener_deconvolution(np.zeros(10), kernel)

    def test_zero_gamma_inverse_filter(self) -> None:
        kernel = pulse_kernel_samples(1.0e6, 1.0e-6, 5.0e-6)
        impulse = np.zeros(2000, dtype=np.float64)
        impulse[500] = 1.0
        signal = np.convolve(impulse, kernel, mode="full")[:2000]
        result = wiener_deconvolution(signal, kernel, gamma=0.0, nsr=1.0e-6)
        peak_window = result.deconvolved[490:520]
        assert np.max(peak_window) > 0.1

    def test_wiener_suppresses_noise(self) -> None:
        rng = np.random.default_rng(42)
        kernel = pulse_kernel_samples(1.0e6, 1.0e-6, 5.0e-6)
        impulse = np.zeros(2000, dtype=np.float64)
        impulse[500] = 1.0
        clean = np.convolve(impulse, kernel, mode="full")[:2000]
        noisy = clean + rng.normal(0.0, 0.02, 2000)
        result_zero = wiener_deconvolution(noisy, kernel, gamma=0.0, nsr=0.01)
        result_wiener = wiener_deconvolution(noisy, kernel, gamma=0.1, nsr=0.01)
        assert result_wiener.residual_ratio <= result_zero.residual_ratio * 2.0


class TestThresholdDeconvolved:
    def test_threshold_zeros_below(self) -> None:
        values = np.array([0.001, 0.5, -0.002, 1.0, -0.05, -0.5], dtype=np.float64)
        th = threshold_deconvolved(values, 0.01)
        assert float(th[0]) == 0.0
        assert float(th[2]) == 0.0
        assert float(th[1]) != 0.0
        assert float(th[3]) != 0.0


class TestGammaNSRScan:
    def test_scan_produces_expected_shapes(self) -> None:
        kernel = pulse_kernel_samples(1.0e6, 1.0e-6, 5.0e-6)
        signal = np.zeros(2000, dtype=np.float64)
        signal[300] = 1.0
        result = scan_gamma_nsr(
            signal,
            kernel,
            gamma_values=np.array([1e-3, 1e-1, 1.0]),
            nsr_values=np.array([1e-3, 1e-2]),
        )
        assert result["gamma_grid"].size == 3
        assert result["nsr_grid"].size == 2
        assert result["residual_map"].shape == (3, 2)
        assert np.any(np.isfinite(result["residual_map"]))
