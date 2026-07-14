from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from he3sim.config import load_config
from he3sim.physics.amplitude import LinearAmplitudeMapper
from he3sim.physics.pulse_parameters import FixedPulseParameterProvider

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_linear_amplitude_mapping_without_spread_is_exact() -> None:
    mapper = LinearAmplitudeMapper(
        gain_V_per_keV=2.0e-4,
        offset_V=0.01,
        spread_std_V=0.0,
        polarity=-1,
    )
    energies = np.array([100.0, 300.0, 764.0], dtype=np.float64)
    result = mapper.sample(energies, np.random.default_rng(1))

    np.testing.assert_allclose(result.amplitude_peak_V, 2.0e-4 * energies + 0.01)
    np.testing.assert_array_equal(result.polarity, -np.ones(3, dtype=np.int16))


def test_broadened_amplitudes_remain_positive_and_reproducible() -> None:
    config = load_config(PROJECT_ROOT / "configs" / "demo_minimal.yaml")
    mapper = LinearAmplitudeMapper.from_config(config.amplitude)
    energies = np.linspace(1.0, 764.0, 5_000)
    left = mapper.sample(energies, np.random.default_rng(99))
    right = mapper.sample(energies, np.random.default_rng(99))

    assert np.all(left.amplitude_peak_V > 0.0)
    np.testing.assert_array_equal(left.amplitude_peak_V, right.amplitude_peak_V)
    assert set(np.unique(left.polarity)) == {1}


def test_provisional_mapper_refuses_missing_calibration() -> None:
    config = load_config(PROJECT_ROOT / "configs" / "provisional_he3.yaml")

    with pytest.raises(ValueError, match="requires calibration"):
        LinearAmplitudeMapper.from_config(config.amplitude)


@pytest.mark.parametrize(
    "mapper",
    [
        lambda: LinearAmplitudeMapper(0.0, 0.0, 0.0, 1),
        lambda: LinearAmplitudeMapper(1.0, 0.0, -1.0, 1),
        lambda: LinearAmplitudeMapper(1.0, 0.0, 0.0, 0),
        lambda: LinearAmplitudeMapper(np.nan, 0.0, 0.0, 1),
    ],
)
def test_amplitude_mapper_rejects_invalid_calibration(mapper: object) -> None:
    with pytest.raises(ValueError):
        mapper()  # type: ignore[operator]


def test_amplitude_mapper_rejects_invalid_energy_arrays() -> None:
    mapper = LinearAmplitudeMapper(1.0e-4, 0.0, 0.0, 1)
    for energies in (
        np.array([-1.0]),
        np.array([np.nan]),
        np.array([np.inf]),
        np.ones((1, 1)),
    ):
        with pytest.raises(ValueError, match="energy_dep_keV"):
            mapper.sample(energies, np.random.default_rng(1))


def test_fixed_pulse_parameter_provider_preserves_alignment_and_future_conditioning_api() -> None:
    provider = FixedPulseParameterProvider(tau_r_s=1.0e-6, tau_d_s=1.0e-5)
    amplitudes = np.array([0.1, 0.2, 0.3], dtype=np.float64)
    components = np.array([0, 1, 2], dtype=np.int16)

    result = provider.sample(amplitudes, components, np.random.default_rng(5))

    np.testing.assert_array_equal(result.tau_r_s, np.full(3, 1.0e-6))
    np.testing.assert_array_equal(result.tau_d_s, np.full(3, 1.0e-5))
    assert result.tau_r_s.shape == amplitudes.shape == components.shape


@pytest.mark.parametrize(
    ("tau_r_s", "tau_d_s"),
    [(0.0, 1.0), (-1.0, 1.0), (1.0, 1.0), (2.0, 1.0), (np.nan, 1.0)],
)
def test_fixed_pulse_parameter_provider_rejects_invalid_time_constants(
    tau_r_s: float,
    tau_d_s: float,
) -> None:
    with pytest.raises(ValueError, match="time constants"):
        FixedPulseParameterProvider(tau_r_s=tau_r_s, tau_d_s=tau_d_s)
