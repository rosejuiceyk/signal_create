from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
import yaml
from pydantic import ValidationError

from he3sim.config import He3SimConfig, load_config
from he3sim.physics.spectra import ParametricHe3Spectrum, SpectrumComponent

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_parametric_spectrum_component_ratios_domains_and_peak() -> None:
    config = load_config(PROJECT_ROOT / "configs" / "demo_minimal.yaml")
    spectrum = ParametricHe3Spectrum.from_config(config.spectrum)
    samples = spectrum.sample(200_000, np.random.default_rng(321))

    assert np.all(samples.energy_dep_keV >= 0.0)
    assert np.all(np.isfinite(samples.energy_dep_keV))
    assert float(np.min(samples.energy_dep_keV)) >= 0.0
    assert float(np.max(samples.energy_dep_keV)) < 850.0
    expected_weights = np.array(spectrum.weights)
    observed_weights = np.bincount(samples.component_id, minlength=4) / samples.component_id.size
    np.testing.assert_allclose(observed_weights, expected_weights, atol=0.004)

    full = samples.energy_dep_keV[samples.component_id == SpectrumComponent.FULL_ENERGY]
    assert np.mean(full) == pytest.approx(spectrum.full_energy_keV, abs=0.15)
    assert np.std(full, ddof=1) == pytest.approx(spectrum.full_energy_sigma_keV, rel=0.02)

    for component, (minimum, maximum, _, _) in (
        (SpectrumComponent.PROTON_WALL, spectrum.proton_wall),
        (SpectrumComponent.TRITON_WALL, spectrum.triton_wall),
        (SpectrumComponent.DOUBLE_WALL, spectrum.double_wall),
    ):
        values = samples.energy_dep_keV[samples.component_id == component]
        assert np.all(values >= minimum)
        assert np.all(values <= maximum)


def test_spectrum_is_reproducible() -> None:
    config = load_config(PROJECT_ROOT / "configs" / "demo_minimal.yaml")
    spectrum = ParametricHe3Spectrum.from_config(config.spectrum)
    left = spectrum.sample(1_000, np.random.default_rng(7))
    right = spectrum.sample(1_000, np.random.default_rng(7))

    np.testing.assert_array_equal(left.energy_dep_keV, right.energy_dep_keV)
    np.testing.assert_array_equal(left.component_id, right.component_id)


def test_configuration_rejects_invalid_mixture_weights() -> None:
    path = PROJECT_ROOT / "configs" / "demo_minimal.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    invalid = deepcopy(raw)
    invalid["spectrum"]["full_energy_fraction"]["value"] = 0.6

    with pytest.raises(ValidationError, match="must sum to one"):
        He3SimConfig.model_validate(invalid)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("proton_wall_fraction", -0.01, "non-negative"),
        ("full_energy_sigma_keV", -1.0, "non-negative"),
        ("proton_wall_alpha", 0.0, "positive"),
        ("triton_wall_max_keV", 765.0, "cannot exceed"),
    ],
)
def test_configuration_rejects_invalid_spectrum_parameters(
    field: str,
    value: float,
    message: str,
) -> None:
    raw = yaml.safe_load((PROJECT_ROOT / "configs" / "demo_minimal.yaml").read_text("utf-8"))
    raw["spectrum"][field]["value"] = value

    with pytest.raises(ValidationError, match=message):
        He3SimConfig.model_validate(raw)


def test_optional_double_wall_component_can_be_disabled_without_invented_parameters() -> None:
    raw = yaml.safe_load((PROJECT_ROOT / "configs" / "demo_minimal.yaml").read_text("utf-8"))
    raw["spectrum"]["full_energy_fraction"]["value"] = 0.6
    raw["spectrum"]["double_wall_fraction"]["value"] = 0.0
    for suffix in ("min_keV", "max_keV", "alpha", "beta"):
        raw["spectrum"][f"double_wall_{suffix}"]["value"] = None
        raw["spectrum"][f"double_wall_{suffix}"]["status"] = "provisional"
    config = He3SimConfig.model_validate(raw)
    spectrum = ParametricHe3Spectrum.from_config(config.spectrum)

    samples = spectrum.sample(20_000, np.random.default_rng(41))

    assert spectrum.double_wall is None
    assert not np.any(samples.component_id == SpectrumComponent.DOUBLE_WALL)


def test_provisional_spectrum_refuses_to_invent_missing_calibration() -> None:
    config = load_config(PROJECT_ROOT / "configs" / "provisional_he3.yaml")

    with pytest.raises(ValueError, match="requires calibration"):
        ParametricHe3Spectrum.from_config(config.spectrum)
