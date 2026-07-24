"""Integration tests for Phase C CLI and validation pipelines."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from he3sim.analysis.continuous_noise import (
    analyze_continuous_noise,
    compute_ccf,
    compute_ctm,
    pulse_kernel_samples,
    scan_gamma_nsr,
    wiener_deconvolution,
)
from he3sim.analysis.phase_c_validation import (
    build_phase_c_validation,
    write_phase_c_validation_report,
)
from he3sim.config import He3SimConfig, load_config


@pytest.fixture(scope="module")
def demo_correlated_config() -> He3SimConfig:
    path = Path("configs/demo_correlated.yaml")
    if not path.exists():
        pytest.skip("demo_correlated.yaml not found")
    return load_config(path)


class TestContinuousNoisePipeline:
    def test_full_analysis_synthetic_signal(self) -> None:
        """End-to-end continuous noise analysis on a minimal synthetic signal."""
        sample_rate = 1.0e6
        tau_r = 1.0e-6
        tau_d = 1.0e-5
        duration = 0.5
        samples = int(duration * sample_rate)
        rng = np.random.default_rng(42)
        voltage = np.zeros(samples, dtype=np.float64)
        from he3sim.physics.pulse_models import double_exponential_peak_value

        peak_val = double_exponential_peak_value(tau_r, tau_d)
        for pos in [1000, 5000, 12000, 18000, 25000, 35000, 45000, 55000, 70000, 85000]:
            kernel_len = min(int(np.ceil(8.0 * tau_d * sample_rate)), samples - pos)
            if kernel_len <= 0:
                continue
            delays = np.arange(kernel_len, dtype=np.float64) / sample_rate
            raw = np.exp(-delays / tau_d) - np.exp(-delays / tau_r)
            voltage[pos : pos + kernel_len] += (raw / peak_val) * 0.1
        voltage += rng.normal(0.0, 0.001, samples)
        analysis = analyze_continuous_noise(
            voltage,
            sample_rate,
            tau_r,
            tau_d,
            1000.0,
            max_lag_s=0.01,
            gate_widths_s=np.geomspace(1.0e-5, 0.002, 24),
        )
        assert analysis.acf_fit.alpha_per_s > 0.0
        assert np.isfinite(analysis.vtm.fit.alpha_per_s)

    def test_three_method_consistency(self) -> None:
        """Continuous ACF, VTM, and deconvolution should all produce finite values."""
        sample_rate = 1.0e6
        tau_r = 1.0e-6
        tau_d = 1.0e-5
        duration = 0.5
        samples = int(duration * sample_rate)
        rng = np.random.default_rng(2025)
        voltage = rng.normal(0.0, 0.005, samples).astype(np.float64)
        from he3sim.physics.pulse_models import double_exponential_peak_value

        peak_val = double_exponential_peak_value(tau_r, tau_d)
        for _ in range(60):
            pos = int(rng.integers(0, samples - 100))
            kernel_len = min(int(np.ceil(6.0 * tau_d * sample_rate)), samples - pos)
            delays = np.arange(kernel_len, dtype=np.float64) / sample_rate
            raw = np.exp(-delays / tau_d) - np.exp(-delays / tau_r)
            voltage[pos : pos + kernel_len] += (raw / peak_val) * 0.1
        analysis = analyze_continuous_noise(
            voltage,
            sample_rate,
            tau_r,
            tau_d,
            1500.0,
            max_lag_s=0.008,
            gate_widths_s=np.geomspace(1.0e-5, 0.002, 24),
        )
        assert np.isfinite(analysis.acf_fit.alpha_per_s)
        assert np.isfinite(analysis.vtm.fit.alpha_per_s)
        assert np.isfinite(analysis.deconv_result.residual_ratio)
        assert analysis.acf_fit.alpha_per_s > 0.0
        assert analysis.vtm.fit.alpha_per_s > 0.0


class TestCCFCTMPipeline:
    def test_ccf_ctm_uncorrelated_channels(self) -> None:
        rng = np.random.default_rng(99)
        sample_rate = 1.0e6
        duration = 0.5
        samples = int(duration * sample_rate)
        v1 = rng.normal(0.0, 0.01, samples).astype(np.float64)
        v2 = rng.normal(0.0, 0.01, samples).astype(np.float64)
        lags, ccf = compute_ccf(v1, v2, 0.005, sample_rate)
        gates, ctm = compute_ctm(v1, v2, sample_rate)
        assert lags.size > 5
        assert float(ccf[0]) == pytest.approx(0.0, abs=0.1)
        assert gates.size > 8


class TestDeconvolutionEndToEnd:
    def test_deconv_then_threshold_isolates_pulses(self) -> None:
        sample_rate = 1.0e6
        tau_r = 1.0e-6
        tau_d = 5.0e-6
        kernel = pulse_kernel_samples(sample_rate, tau_r, tau_d)
        signal = np.zeros(4000, dtype=np.float64)
        positions = [400, 1400, 2400, 3400]
        from he3sim.physics.pulse_models import double_exponential_peak_value

        peak_val = double_exponential_peak_value(tau_r, tau_d)
        for pos in positions:
            kernel_len = min(kernel.size, signal.size - pos)
            signal[pos : pos + kernel_len] += kernel[:kernel_len] * 0.5 / peak_val
        result = wiener_deconvolution(signal, kernel, gamma=0.001, nsr=0.001)
        threshold = 2.0 * np.std(result.deconvolved)
        peaks = np.where(np.abs(result.deconvolved) > threshold)[0]
        for pos in positions:
            assert np.any(np.abs(peaks - pos) < 5)

    def test_gamma_nsr_scan_varied(self) -> None:
        kernel = pulse_kernel_samples(1.0e6, 1.0e-6, 5.0e-6)
        signal = np.zeros(2000, dtype=np.float64)
        signal[500] = 1.0
        scan = scan_gamma_nsr(signal, kernel)
        assert scan["gamma_grid"].size > 5
        assert scan["nsr_grid"].size > 3
        finite = np.isfinite(scan["residual_map"])
        assert np.sum(finite) > 0


class TestValidationArtifacts:
    def test_build_artifacts_returns_structured_data(
        self, demo_correlated_config: He3SimConfig
    ) -> None:
        artifacts = build_phase_c_validation(
            demo_correlated_config,
            recovery_events=8_000,
            dual_events=5_000,
            frontier_events=4_000,
        )
        assert len(artifacts.recovery_points) > 0
        assert len(artifacts.frontier_points) > 0
        assert artifacts.ccf_lags.size > 0
        assert artifacts.primary_voltage.size > 0
        assert np.isfinite(artifacts.metrics.maximum_continuous_acf_error)

    def test_write_report_produces_files(
        self, demo_correlated_config: He3SimConfig, tmp_path: Path
    ) -> None:
        artifacts = build_phase_c_validation(
            demo_correlated_config,
            recovery_events=8_000,
            dual_events=5_000,
            frontier_events=4_000,
        )
        report = write_phase_c_validation_report(tmp_path, demo_correlated_config, artifacts)
        assert report.exists()
        assert (tmp_path / "phase_c_validation.json").exists()
        assert (tmp_path / "continuous_acf_fit.png").exists()
        assert (tmp_path / "usability_frontier.png").exists()
        payload = json.loads((tmp_path / "phase_c_validation.json").read_text(encoding="utf-8"))
        assert "metrics" in payload
