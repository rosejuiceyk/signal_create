from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import yaml
from typer.testing import CliRunner

from he3sim.cli import app
from he3sim.config import He3SimConfig, SourceModelKind, load_config
from he3sim.io.dataset import write_dataset_hdf5
from he3sim.synthesis.dataset import prepare_dataset_simulation

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER = CliRunner()


def observation_config() -> He3SimConfig:
    config = load_config(PROJECT_ROOT / "configs" / "demo_minimal.yaml")
    raw = config.model_dump(mode="python")
    raw["simulation"]["true_rate_cps"]["value"] = 3.0e4
    raw["simulation"]["sample_rate_hz"]["value"] = 100.0e6
    raw["observation"]["duration_s"]["value"] = 1.0e-3
    raw["dataset"]["continuous_duration_s"]["value"] = 1.0e-3
    raw["dataset"]["max_windows"]["value"] = 16
    raw["waveform"]["max_samples_per_block"]["value"] = 256
    raw["noise"]["enabled"] = False
    raw["baseline"]["enabled"] = False
    raw["trigger"]["threshold_V"]["value"] = 0.01
    raw["trigger"]["hysteresis_V"]["value"] = 0.005
    raw["trigger"]["min_hold_s"]["value"] = 0.0
    raw["trigger"]["pre_trigger_s"]["value"] = 5.0e-6
    raw["trigger"]["post_trigger_s"]["value"] = 30.0e-6
    raw["dead_time"]["duration_s"]["value"] = 100.0e-6
    return He3SimConfig.model_validate(raw)


def test_rejected_triggers_leave_truth_and_waveform_unchanged(tmp_path: Path) -> None:
    config = observation_config()
    plan = prepare_dataset_simulation(config, max_expected_events=1_000)
    output = write_dataset_hdf5(tmp_path / "observation.h5", plan, config)

    with h5py.File(output, "r") as handle:
        true_events = np.asarray(handle["events/true"])
        observed = np.asarray(handle["events/observed"])
        links = np.asarray(handle["events/trigger_event_links"])
        rejected_ids = observed["trigger_id"][~observed["accepted"]]
        assert rejected_ids.size > 0
        rejected_links = links[np.isin(links["trigger_id"], rejected_ids)]
        assert rejected_links.size > 0
        assert np.all(np.isin(rejected_links["event_id"], true_events["event_id"]))
        assert int(np.sum(handle["blocks/index"]["event_count"])) == true_events.size
        assert handle["blocks/analog_samples"].shape == (plan.waveform.sample_count,)


def test_phase3_cli_dataset_and_validation(tmp_path: Path) -> None:
    config = observation_config()
    config_path = tmp_path / "phase3.yaml"
    config_path.write_text(
        yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    dataset_result = RUNNER.invoke(
        app,
        ["generate-dataset", "-c", str(config_path), "-o", str(tmp_path / "dataset")],
    )
    assert dataset_result.exit_code == 0, dataset_result.output
    assert "truth_events:" in dataset_result.output
    assert (tmp_path / "dataset" / "dataset.h5").exists()

    validation_result = RUNNER.invoke(
        app,
        [
            "validate-physics",
            "-c",
            str(config_path),
            "-o",
            str(tmp_path / "validation"),
            "--replicates",
            "30",
        ],
    )
    assert validation_result.exit_code == 0, validation_result.output
    assert "standard_rates: 13" in validation_result.output
    assert "result: passed" in validation_result.output


def test_correlated_events_run_through_waveform_trigger_dead_time_and_dataset(
    tmp_path: Path,
) -> None:
    config = observation_config()
    raw = config.model_dump(mode="python")
    raw["source_model"]["kind"] = SourceModelKind.CORRELATED.value
    raw["source_model"]["source_rate_cps"]["value"] = 240_000.0
    correlated = He3SimConfig.model_validate(raw)

    plan = prepare_dataset_simulation(correlated, max_expected_events=1_000)
    output = write_dataset_hdf5(tmp_path / "correlated-dataset.h5", plan, correlated)

    with h5py.File(output, "r") as handle:
        truth = np.asarray(handle["events/true"])
        lineage = np.asarray(handle["events/lineage"])
        assert truth.size > 0
        assert lineage.shape == truth.shape
        np.testing.assert_array_equal(lineage["event_id"], truth["event_id"])
        assert handle["blocks/analog_samples"].shape == (plan.waveform.sample_count,)
        assert "observed" in handle["events"]
        assert "trigger_event_links" in handle["events"]
        assert handle["metadata"].attrs["source_model"] == "correlated"
