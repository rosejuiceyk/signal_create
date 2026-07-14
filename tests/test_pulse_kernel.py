from __future__ import annotations

import numpy as np
import pytest

from he3sim.analysis.pulse_features import extract_pulse_features
from he3sim.physics.pulse_models import (
    PulseResolutionWarning,
    double_exponential_peak_time_s,
    normalized_double_exponential,
    warn_if_time_constants_under_resolved,
)
from he3sim.synthesis.renderers import render_direct_sparse
from he3sim.types import TRUE_EVENT_DTYPE


def one_event(
    t_s: float,
    amplitude_peak_V: float = 0.25,
    polarity: int = 1,
    tau_r_s: float = 20.0e-9,
    tau_d_s: float = 200.0e-9,
) -> np.ndarray:
    events = np.zeros(1, dtype=TRUE_EVENT_DTYPE)
    events["event_id"] = 0
    events["t_s"] = t_s
    events["energy_dep_keV"] = 764.0
    events["amplitude_peak_V"] = amplitude_peak_V
    events["tau_r_s"] = tau_r_s
    events["tau_d_s"] = tau_d_s
    events["polarity"] = polarity
    events["parameter_status"] = b"synthetic_demo"
    return events


def test_continuous_double_exponential_has_unit_analytic_peak() -> None:
    tau_r_s = 20.0e-9
    tau_d_s = 200.0e-9
    peak_time_s = double_exponential_peak_time_s(tau_r_s, tau_d_s)

    assert peak_time_s > 0.0
    assert normalized_double_exponential(peak_time_s, tau_r_s, tau_d_s) == pytest.approx(1.0)
    assert normalized_double_exponential(-1.0e-9, tau_r_s, tau_d_s) == 0.0


@pytest.mark.parametrize("polarity", [-1, 1])
def test_discrete_single_pulse_peak_equals_target_for_fractional_onset(polarity: int) -> None:
    sample_rate_hz = 100.0e6
    amplitude_peak_V = 0.25
    events = one_event(3.25 / sample_rate_hz, amplitude_peak_V, polarity)

    waveform = render_direct_sparse(events, 300, sample_rate_hz)

    measured_peak = float(np.max(polarity * waveform))
    assert measured_peak == pytest.approx(amplitude_peak_V, rel=1.0e-12, abs=1.0e-15)
    assert np.all(waveform[:4] == 0.0)


def test_sampled_pulse_features_are_measured_from_waveform() -> None:
    sample_rate_hz = 250.0e6
    events = one_event(8.0 / sample_rate_hz, amplitude_peak_V=0.4)
    waveform = render_direct_sparse(events, 1_000, sample_rate_hz)

    features = extract_pulse_features(waveform, sample_rate_hz, polarity=1)

    assert features.peak_V == pytest.approx(0.4, rel=1.0e-12)
    assert features.integral_V_s > 0.0
    assert features.rise_time_10_90_s > 0.0
    assert features.fall_time_90_10_s > 0.0
    assert features.rise_time_10_90_s != pytest.approx(float(events["tau_r_s"][0]))


def test_under_resolved_time_constant_emits_explicit_warning() -> None:
    with pytest.warns(PulseResolutionWarning, match="under-resolved"):
        warn_if_time_constants_under_resolved(100.0e6, 1.0e-9, 20.0e-9)
