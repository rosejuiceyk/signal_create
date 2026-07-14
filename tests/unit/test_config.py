from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from he3sim.config import (
    He3SimConfig,
    ParameterStatus,
    ParameterValue,
    config_hash,
    load_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def parameter_records(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        if "value" in value and "status" in value:
            yield value
        for child in value.values():
            yield from parameter_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from parameter_records(child)


def load_raw(name: str) -> dict[str, Any]:
    path = PROJECT_ROOT / "configs" / name
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def test_demo_configuration_is_valid_and_entirely_synthetic() -> None:
    config = load_config(PROJECT_ROOT / "configs" / "demo_minimal.yaml")
    records = list(parameter_records(config.model_dump(mode="json")))

    assert records
    assert {record["status"] for record in records} == {"synthetic_demo"}
    assert len(config_hash(config)) == 64


def test_provisional_configuration_preserves_pending_calibration_values() -> None:
    config = load_config(PROJECT_ROOT / "configs" / "provisional_he3.yaml")

    assert config.amplitude.gain_V_per_keV.value is None
    assert config.pulse_shape.tau_r_s.value is None
    assert config.adc.bits.value is None
    assert config.amplitude.gain_V_per_keV.status is ParameterStatus.PROVISIONAL


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("simulation", "true_rate_cps", 9.0),
        ("simulation", "true_rate_cps", 1.0e7 + 1.0),
        ("simulation", "sample_rate_hz", 99.0e6),
        ("simulation", "sample_rate_hz", 251.0e6),
    ],
)
def test_operating_domain_bounds_are_enforced(section: str, field: str, value: float) -> None:
    raw = load_raw("demo_minimal.yaml")
    raw[section][field]["value"] = value

    with pytest.raises(ValidationError):
        He3SimConfig.model_validate(raw)


def test_observation_mode_fields_are_mutually_exclusive() -> None:
    raw = load_raw("demo_minimal.yaml")
    raw["observation"]["target_event_count"] = {
        "value": 10,
        "status": "synthetic_demo",
    }

    with pytest.raises(ValidationError, match="cannot set target_event_count"):
        He3SimConfig.model_validate(raw)


def test_target_event_duration_is_clamped_by_explicit_bounds() -> None:
    raw = load_raw("demo_minimal.yaml")
    raw["observation"] = {
        "mode": "target_event_count",
        "target_event_count": {"value": 100, "status": "synthetic_demo"},
        "min_duration_s": {"value": 0.2, "status": "synthetic_demo"},
        "max_duration_s": {"value": 1.0, "status": "synthetic_demo"},
    }
    config = He3SimConfig.model_validate(raw)

    from he3sim.physics.events import resolve_duration_s

    assert resolve_duration_s(config) == 0.2


def test_phase3_trigger_and_dataset_guards_are_validated() -> None:
    excessive_hysteresis = load_raw("demo_minimal.yaml")
    excessive_hysteresis["trigger"]["hysteresis_V"]["value"] = 0.01
    with pytest.raises(ValidationError, match="below threshold"):
        He3SimConfig.model_validate(excessive_hysteresis)

    invalid_windows = load_raw("demo_minimal.yaml")
    invalid_windows["dataset"]["max_windows"]["value"] = 0
    with pytest.raises(ValidationError, match="max_windows"):
        He3SimConfig.model_validate(invalid_windows)


def test_time_constant_order_is_enforced() -> None:
    raw = load_raw("demo_minimal.yaml")
    raw["pulse_shape"]["tau_d_s"]["value"] = raw["pulse_shape"]["tau_r_s"]["value"]

    with pytest.raises(ValidationError, match="greater than tau_r_s"):
        He3SimConfig.model_validate(raw)


def test_validated_parameter_requires_value_and_source() -> None:
    with pytest.raises(ValidationError, match="evidence source"):
        ParameterValue[int](value=1, status=ParameterStatus.VALIDATED)

    with pytest.raises(ValidationError, match="must have a value"):
        ParameterValue[int](
            value=None,
            status=ParameterStatus.VALIDATED,
            source="reviewed calibration",
        )


def test_validated_parameter_requires_explicit_human_review() -> None:
    with pytest.raises(ValidationError, match="human reviewer"):
        ParameterValue[int](
            value=1,
            status=ParameterStatus.VALIDATED,
            source="calibration/run-001",
        )

    with pytest.raises(ValidationError, match="timezone-aware"):
        ParameterValue[int](
            value=1,
            status=ParameterStatus.VALIDATED,
            source="calibration/run-001",
            reviewed_by="reviewer@example.invalid",
            reviewed_at=datetime(2026, 7, 13),
        )

    parameter = ParameterValue[int](
        value=1,
        status=ParameterStatus.VALIDATED,
        source="calibration/run-001",
        reviewed_by="reviewer@example.invalid",
        reviewed_at=datetime(2026, 7, 13, tzinfo=UTC),
    )
    assert parameter.status is ParameterStatus.VALIDATED


@pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_configuration_values_are_rejected(non_finite: float) -> None:
    raw = load_raw("demo_minimal.yaml")
    raw["simulation"]["true_rate_cps"]["value"] = non_finite

    with pytest.raises(ValidationError):
        He3SimConfig.model_validate(raw)


def test_invalid_seed_missing_field_and_unit_bearing_value_are_rejected() -> None:
    negative_seed = load_raw("demo_minimal.yaml")
    negative_seed["metadata"]["seed"]["value"] = -1
    with pytest.raises(ValidationError, match="seed"):
        He3SimConfig.model_validate(negative_seed)

    boolean_seed = load_raw("demo_minimal.yaml")
    boolean_seed["metadata"]["seed"]["value"] = True
    with pytest.raises(ValidationError, match="integer"):
        He3SimConfig.model_validate(boolean_seed)

    missing_field = load_raw("demo_minimal.yaml")
    del missing_field["spectrum"]["full_energy_sigma_keV"]
    with pytest.raises(ValidationError, match="full_energy_sigma_keV"):
        He3SimConfig.model_validate(missing_field)

    invalid_unit = load_raw("demo_minimal.yaml")
    invalid_unit["simulation"]["true_rate_cps"]["value"] = "1000 Hz"
    with pytest.raises(ValidationError, match="valid number"):
        He3SimConfig.model_validate(invalid_unit)


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    [
        ("observation", "duration_s", 0.0, "positive"),
        ("observation", "duration_s", -1.0, "positive"),
        ("pulse_shape", "tau_r_s", -1.0, "positive"),
        ("pulse_shape", "tau_d_s", -1.0, "positive"),
    ],
)
def test_phase1_time_boundaries_are_rejected(
    section: str,
    field: str,
    value: float,
    message: str,
) -> None:
    raw = load_raw("demo_minimal.yaml")
    raw[section][field]["value"] = value

    with pytest.raises(ValidationError, match=message):
        He3SimConfig.model_validate(raw)


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    [
        ("waveform", "max_samples_per_block", 0, "positive"),
        ("adc", "bits", 0, "within"),
        ("adc", "bits", 17, "within"),
        ("noise", "low_frequency_drift_rms_V", -1.0, "non-negative"),
        ("noise", "low_frequency_drift_correlation_s", 0.0, "positive"),
    ],
)
def test_phase2_configuration_boundaries_are_rejected(
    section: str,
    field: str,
    value: float,
    message: str,
) -> None:
    raw = load_raw("demo_minimal.yaml")
    raw[section][field]["value"] = value

    with pytest.raises(ValidationError, match=message):
        He3SimConfig.model_validate(raw)


def test_phase2_voltage_ranges_and_enabled_drift_parameters_are_validated() -> None:
    invalid_clip = load_raw("demo_minimal.yaml")
    invalid_clip["waveform"]["analog_clip_max_V"]["value"] = -1.0
    with pytest.raises(ValidationError, match="analog_clip_max_V"):
        He3SimConfig.model_validate(invalid_clip)

    missing_drift = load_raw("demo_minimal.yaml")
    missing_drift["noise"]["low_frequency_drift_enabled"] = True
    missing_drift["noise"]["low_frequency_drift_rms_V"]["value"] = None
    missing_drift["noise"]["low_frequency_drift_rms_V"]["status"] = "provisional"
    with pytest.raises(ValidationError, match="requires RMS"):
        He3SimConfig.model_validate(missing_drift)


def test_config_hash_is_order_independent_and_value_sensitive() -> None:
    raw = load_raw("demo_minimal.yaml")
    reordered = dict(reversed(list(raw.items())))
    modified = deepcopy(raw)
    modified["metadata"]["seed"]["value"] += 1

    original_hash = config_hash(He3SimConfig.model_validate(raw))
    assert config_hash(He3SimConfig.model_validate(reordered)) == original_hash
    assert config_hash(He3SimConfig.model_validate(modified)) != original_hash


def test_schema_artifact_matches_pydantic_model() -> None:
    schema_path = PROJECT_ROOT / "configs" / "schemas" / "he3sim.schema.json"
    generated = He3SimConfig.model_json_schema()
    committed = yaml.safe_load(schema_path.read_text(encoding="utf-8"))

    assert committed == generated
