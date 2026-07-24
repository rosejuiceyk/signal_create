from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
from typer.testing import CliRunner

from he3sim.cli import app
from he3sim.config import He3SimConfig, SourceModelKind, config_hash, load_config
from he3sim.io.hdf5 import read_true_events_hdf5, write_true_events_hdf5
from he3sim.physics.arrivals import ArrivalAlgorithm
from he3sim.physics.events import simulate_true_events

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER = CliRunner()


def test_truth_event_pipeline_is_reproducible_and_memory_guarded() -> None:
    config = load_config(PROJECT_ROOT / "configs" / "demo_minimal.yaml")
    left = simulate_true_events(config, ArrivalAlgorithm.POISSON_UNIFORM)
    right = simulate_true_events(config, ArrivalAlgorithm.POISSON_UNIFORM)

    np.testing.assert_array_equal(left.events, right.events)
    if left.events.size:
        assert np.all(np.diff(left.events["t_s"]) > 0.0)
        assert np.all(left.events["energy_dep_keV"] >= 0.0)
        assert np.all(left.events["amplitude_peak_V"] > 0.0)
        assert np.all(left.events["tau_r_s"] > 0.0)
        assert np.all(left.events["tau_d_s"] > left.events["tau_r_s"])
        assert set(np.unique(left.events["polarity"])) <= {-1, 1}

    guarded_config = config.model_copy(deep=True)
    assert guarded_config.observation.duration_s is not None
    guarded_config.observation.duration_s.value = 0.01
    with np.testing.assert_raises_regex(ValueError, "in-memory limit"):
        simulate_true_events(guarded_config, max_expected_events=1)


def test_target_event_count_mode_sets_expected_horizon_and_is_memory_guarded() -> None:
    config = load_config(PROJECT_ROOT / "configs" / "demo_minimal.yaml")
    raw = config.model_dump(mode="python")
    raw["observation"] = {
        "mode": "target_event_count",
        "target_event_count": {"value": 250, "status": "synthetic_demo"},
    }
    target_config = He3SimConfig.model_validate(raw)

    simulation = simulate_true_events(target_config, max_expected_events=1_000)

    assert simulation.duration_s == 0.25
    assert simulation.true_rate_cps * simulation.duration_s == 250.0

    raw["observation"]["target_event_count"]["value"] = 2_000_000
    oversized = He3SimConfig.model_validate(raw)
    with np.testing.assert_raises_regex(ValueError, "in-memory limit"):
        simulate_true_events(oversized)


def test_trigger_and_dead_time_placeholders_do_not_filter_truth_events() -> None:
    config = load_config(PROJECT_ROOT / "configs" / "demo_minimal.yaml")
    baseline = simulate_true_events(config)
    raw = config.model_dump(mode="python")
    raw["trigger"]["enabled"] = True
    raw["dead_time"]["mode"] = "nonparalyzable"
    raw["dead_time"]["duration_s"]["value"] = 1.0e-4
    placeholders_enabled = He3SimConfig.model_validate(raw)

    comparison = simulate_true_events(placeholders_enabled)

    np.testing.assert_array_equal(comparison.events, baseline.events)


def test_hdf5_truth_table_round_trip_and_metadata(tmp_path: Path) -> None:
    config = load_config(PROJECT_ROOT / "configs" / "demo_minimal.yaml")
    simulation = simulate_true_events(config)
    output = write_true_events_hdf5(tmp_path / "events.h5", simulation, config)
    events, metadata = read_true_events_hdf5(output)

    np.testing.assert_array_equal(events, simulation.events)
    assert metadata["config_hash"] == config_hash(config)
    assert metadata["seed"] == config.metadata.seed.value
    assert metadata["parameter_status"] == "synthetic_demo"
    assert json.loads(metadata["units_json"])["t_s"] == "s"
    with h5py.File(output, "r") as handle:
        assert set(handle) == {"events", "metadata"}
        assert set(handle["events"]) == {"true"}
        assert "blocks" not in handle
        assert "adc" not in handle


def test_empty_truth_event_result_has_stable_structure_and_round_trips(tmp_path: Path) -> None:
    config = load_config(PROJECT_ROOT / "configs" / "demo_minimal.yaml")
    raw = config.model_dump(mode="python")
    raw["observation"]["duration_s"]["value"] = 1.0e-9
    empty_config = He3SimConfig.model_validate(raw)
    simulation = simulate_true_events(empty_config)

    assert simulation.events.shape == (0,)
    assert simulation.events.dtype.names is not None
    output = write_true_events_hdf5(tmp_path / "empty_events.h5", simulation, empty_config)
    restored, metadata = read_true_events_hdf5(output)
    assert restored.shape == (0,)
    assert restored.dtype == simulation.events.dtype
    assert metadata["true_rate_cps"] == 1_000.0


def test_phase1_cli_simulation_and_validation(tmp_path: Path) -> None:
    config_path = PROJECT_ROOT / "configs" / "demo_minimal.yaml"
    hdf5_path = tmp_path / "phase01_events.h5"
    validation_path = tmp_path / "validation"

    simulation = RUNNER.invoke(
        app,
        ["simulate-events", "-c", str(config_path), "-o", str(hdf5_path)],
    )
    assert simulation.exit_code == 0, simulation.output
    assert hdf5_path.exists()
    assert "truth events" in simulation.output

    validation = RUNNER.invoke(
        app,
        [
            "validate-arrivals",
            "-c",
            str(config_path),
            "-o",
            str(validation_path),
            "--replicates",
            "100",
        ],
    )
    assert validation.exit_code == 0, validation.output
    assert "result: passed" in validation.output
    assert (validation_path / "arrival_validation.json").exists()
    assert (validation_path / "arrival_validation.md").exists()
    assert (validation_path / "count_histogram.png").exists()
    assert (validation_path / "interval_cdf.png").exists()


def test_correlated_truth_pipeline_persists_lineage_without_changing_truth_dtype(
    tmp_path: Path,
) -> None:
    config = load_config(PROJECT_ROOT / "configs" / "demo_minimal.yaml")
    raw = config.model_dump(mode="python")
    raw["source_model"]["kind"] = SourceModelKind.CORRELATED.value
    correlated = He3SimConfig.model_validate(raw)

    left = simulate_true_events(correlated)
    right = simulate_true_events(correlated)

    np.testing.assert_array_equal(left.events, right.events)
    assert left.source_model is SourceModelKind.CORRELATED
    assert left.lineage is not None
    assert left.lineage.shape == left.events.shape
    np.testing.assert_array_equal(left.lineage["event_id"], left.events["event_id"])
    assert np.all(left.events["pileup_group_id"] == -1)
    output = write_true_events_hdf5(tmp_path / "correlated.h5", left, correlated)
    with h5py.File(output, "r") as handle:
        assert set(handle["events"]) == {"true", "lineage"}
        assert handle["metadata"].attrs["source_model"] == "correlated"
        assert "source_model_derived_json" in handle["metadata"].attrs


def test_correlated_expected_reaction_guard_fails_before_generation() -> None:
    config = load_config(PROJECT_ROOT / "configs" / "demo_minimal.yaml")
    raw = config.model_dump(mode="python")
    raw["source_model"]["kind"] = SourceModelKind.CORRELATED.value
    raw["source_model"]["max_total_reactions"] = 10
    guarded = He3SimConfig.model_validate(raw)

    with np.testing.assert_raises_regex(ValueError, "expected branching reactions"):
        simulate_true_events(guarded)


def test_phase_a_cli_source_override_uses_correlated_preset(tmp_path: Path) -> None:
    result = RUNNER.invoke(
        app,
        [
            "simulate-events",
            "-c",
            str(PROJECT_ROOT / "configs" / "demo_minimal.yaml"),
            "-o",
            str(tmp_path / "phase_a.h5"),
            "--source-model",
            "correlated",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "source_model: correlated" in result.output
    with h5py.File(tmp_path / "phase_a.h5", "r") as handle:
        assert "lineage" in handle["events"]
