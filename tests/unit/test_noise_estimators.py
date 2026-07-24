from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.figure import Figure

from he3sim.analysis.figures import (
    phase_b_feynman_figure,
    phase_b_psd_figure,
    phase_b_rossi_figure,
)
from he3sim.analysis.noise import (
    feynman_alpha,
    feynman_model,
    hazama_vtm_correction,
    refit_feynman_curve,
    rossi_alpha,
)


def test_feynman_fit_recovers_alpha_from_precomputed_data() -> None:
    gates = np.geomspace(2.0e-5, 0.01, 32)
    alpha_true = 1_250.0
    values = feynman_model(gates, alpha_true, 0.72)

    curve = refit_feynman_curve(gates, values)

    assert curve.fit.alpha_per_s == pytest.approx(alpha_true, rel=1.0e-6)
    assert curve.fit.amplitude == pytest.approx(0.72, rel=1.0e-6)


def test_poisson_input_has_small_rossi_correlation_amplitude() -> None:
    rng = np.random.default_rng(42)
    duration_s = 60.0
    event_count = rng.poisson(2_000.0 * duration_s)
    times = np.sort(rng.uniform(0.0, duration_s, event_count))

    curve = rossi_alpha(times, duration_s)

    assert curve.fit.amplitude / curve.fit.baseline < 0.03


def test_poisson_input_has_small_feynman_excess() -> None:
    rng = np.random.default_rng(43)
    duration_s = 50.0
    times = np.sort(rng.uniform(0.0, duration_s, 100_000))

    curve = feynman_alpha(times, duration_s)

    assert curve.fit.amplitude < 0.01


def test_hazama_first_order_lift_is_data_only() -> None:
    observed = np.array([-0.02, 0.1, 0.3])
    corrected = hazama_vtm_correction(observed, 4_000.0, 2.0e-5)
    np.testing.assert_allclose(corrected, observed + 0.16)


def test_hazama_lift_reduces_known_feynman_intercept_bias() -> None:
    gates = np.geomspace(2.0e-5, 0.01, 32)
    alpha_true = 1_000.0
    ideal = feynman_model(gates, alpha_true, 0.8)
    observed_rate = 4_000.0
    dead_time_s = 2.0e-5
    observed = ideal - 2.0 * observed_rate * dead_time_s

    raw = refit_feynman_curve(gates, observed)
    corrected = refit_feynman_curve(
        gates, hazama_vtm_correction(observed, observed_rate, dead_time_s)
    )

    assert abs(corrected.fit.alpha_per_s - alpha_true) < abs(raw.fit.alpha_per_s - alpha_true)


def test_phase_b_fit_figures_are_pure_and_use_chinese_labels() -> None:
    x = np.geomspace(1.0e-4, 1.0e-2, 12)
    y = np.linspace(1.0, 2.0, 12)
    figures = (
        phase_b_rossi_figure(x, y, y, 1_000.0, 1_000.0, 1.0, 1.0),
        phase_b_feynman_figure(x, y, y, 1_000.0, 1_000.0, 0.5),
        phase_b_psd_figure(x * 1.0e5, y, y, 1_000.0, 1_000.0, 0.5),
    )
    try:
        assert all(isinstance(figure, Figure) for figure in figures)
        assert all("Phase B" in figure._suptitle.get_text() for figure in figures)
        assert any("时间" in axis.get_xlabel() for axis in figures[0].axes)
        assert any("门宽" in axis.get_xlabel() for axis in figures[1].axes)
        assert any("频率" in axis.get_xlabel() for axis in figures[2].axes)
    finally:
        for figure in figures:
            plt.close(figure)
