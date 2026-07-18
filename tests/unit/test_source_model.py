from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from he3sim.config import He3SimConfig, SourceModelKind, load_config
from he3sim.physics.source_model import PromptSourceModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def demo_raw() -> dict[str, object]:
    raw = yaml.safe_load((PROJECT_ROOT / "configs" / "demo_minimal.yaml").read_text("utf-8"))
    assert isinstance(raw, dict)
    return raw


def test_prompt_source_model_maps_inputs_to_expected_rates() -> None:
    config = load_config(PROJECT_ROOT / "configs" / "demo_minimal.yaml")
    model = PromptSourceModel.from_config(config.source_model)

    assert model.k_eff == pytest.approx(0.2)
    assert model.reactivity == pytest.approx(-4.0)
    assert model.lambda_t_per_s == pytest.approx(1_250.0)
    assert model.lambda_f_per_s == pytest.approx(100.0)
    assert model.lambda_d_per_s == pytest.approx(125.0)
    assert model.lambda_c_per_s == pytest.approx(1_025.0)
    assert model.mean_reaction_time_s == pytest.approx(1.0 / 1_250.0)
    assert model.generation_time_s == pytest.approx(1.0 / 250.0)
    assert model.diven_factor == pytest.approx(0.64)
    assert model.expected_detected_rate_cps == pytest.approx(1_000.0)


def test_negative_reactivity_can_replace_direct_k_eff() -> None:
    raw = demo_raw()
    source = raw["source_model"]  # type: ignore[index]
    assert isinstance(source, dict)
    source["kind"] = SourceModelKind.CORRELATED.value
    source.pop("k_eff")
    source["reactivity"] = {"value": -4.0, "status": "synthetic_demo"}

    config = He3SimConfig.model_validate(raw)

    assert config.source_model.resolved_k_eff() == pytest.approx(0.2)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (("nu_pmf", [0.0, 0.0, 0.4, 0.4]), "sum to one"),
        (("nu_bar", 2.4), "mean of nu_pmf"),
        (("detection_efficiency", 0.95), "k_eff/nu_bar"),
        (("k_eff", 1.0), "0 < k_eff < 1"),
    ],
)
def test_invalid_correlated_physics_is_rejected(
    mutation: tuple[str, float | list[float]],
    message: str,
) -> None:
    raw = demo_raw()
    source = raw["source_model"]  # type: ignore[index]
    assert isinstance(source, dict)
    source["kind"] = SourceModelKind.CORRELATED.value
    field, value = mutation
    parameter = source[field]
    assert isinstance(parameter, dict)
    parameter["value"] = value

    with pytest.raises(ValidationError, match=message):
        He3SimConfig.model_validate(raw)


def test_configured_truth_rate_must_match_branching_first_moment() -> None:
    raw = deepcopy(demo_raw())
    source = raw["source_model"]  # type: ignore[index]
    assert isinstance(source, dict)
    source["kind"] = SourceModelKind.CORRELATED.value
    simulation = raw["simulation"]  # type: ignore[index]
    assert isinstance(simulation, dict)
    true_rate = simulation["true_rate_cps"]
    assert isinstance(true_rate, dict)
    true_rate["value"] = 999.0

    with pytest.raises(ValidationError, match=r"S\*epsilon"):
        He3SimConfig.model_validate(raw)
