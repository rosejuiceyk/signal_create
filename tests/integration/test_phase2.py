from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
from typer.testing import CliRunner

from he3sim.cli import app
from he3sim.config import He3SimConfig, WaveformRenderer, load_config
from he3sim.io.hdf5 import inspect_hdf5, write_waveform_hdf5
from he3sim.synthesis.streaming import iter_waveform_blocks, prepare_waveform_simulation

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER = CliRunner()


def compact_waveform_config() -> He3SimConfig:
    config = load_config(PROJECT_ROOT / "configs" / "demo_minimal.yaml")
    raw = config.model_dump(mode="python")
    raw["simulation"]["true_rate_cps"]["value"] = 1.0e7
    raw["simulation"]["sample_rate_hz"]["value"] = 100.0e6
    raw["observation"]["duration_s"]["value"] = 5.0e-6
    raw["waveform"]["max_samples_per_block"]["value"] = 128
    return He3SimConfig.model_validate(raw)


def test_phase2_streaming_hdf5_is_reproducible_and_contains_no_phase3_data(
    tmp_path: Path,
) -> None:
    config = compact_waveform_config()
    simulation = prepare_waveform_simulation(config)
    expected_blocks = list(iter_waveform_blocks(simulation, config))
    output = write_waveform_hdf5(tmp_path / "waveform.h5", simulation, config)

    with h5py.File(output, "r") as handle:
        assert set(handle) == {"blocks", "events", "metadata"}
        assert set(handle["events"]) == {"true"}
        assert set(handle["blocks"]) == {
            "adc_samples",
            "analog_samples",
            "index",
            "preclip_analog_samples",
            "saturation_mask",
        }
        assert "observed" not in handle["events"]
        assert "windows" not in handle
        assert "trigger_event_links" not in handle["events"]
        events = np.asarray(handle["events/true"])
        assert events.size == simulation.true_events.events.size
        assert np.all(events["sample_index"] >= 0)
        assert np.all(events["block_id"] == events["sample_index"] // simulation.block_size)
        index = np.asarray(handle["blocks/index"])
        assert int(np.sum(index["length"])) == simulation.sample_count
        assert int(np.sum(index["event_count"])) == events.size
        expected_analog = np.concatenate(
            [
                block.analog_samples_V
                for block in expected_blocks
                if block.analog_samples_V is not None
            ]
        )
        expected_preclip_analog = np.concatenate(
            [
                block.preclip_analog_samples_V
                for block in expected_blocks
                if block.preclip_analog_samples_V is not None
            ]
        )
        expected_adc = np.concatenate(
            [block.adc_samples for block in expected_blocks if block.adc_samples is not None]
        )
        np.testing.assert_array_equal(handle["blocks/analog_samples"], expected_analog)
        np.testing.assert_array_equal(
            handle["blocks/preclip_analog_samples"],
            expected_preclip_analog,
        )
        assert np.max(handle["blocks/preclip_analog_samples"]) > 1.0
        assert np.max(handle["blocks/analog_samples"]) <= 1.0
        np.testing.assert_array_equal(handle["blocks/adc_samples"], expected_adc)
        assert handle["metadata"].attrs["renderer"] == "recursive_fixed_tau"
        assert handle["metadata"].attrs["parameter_status"] == "synthetic_demo"

    summary = inspect_hdf5(output)
    assert summary["/blocks/adc_samples"]["shape"] == [simulation.sample_count]


def test_waveform_sample_guard_and_provisional_run_gate() -> None:
    config = compact_waveform_config()
    with np.testing.assert_raises_regex(ValueError, "sample count"):
        prepare_waveform_simulation(config, max_waveform_samples=10)

    provisional = load_config(PROJECT_ROOT / "configs" / "provisional_he3.yaml")
    with np.testing.assert_raises_regex(ValueError, "requires analog or ADC"):
        prepare_waveform_simulation(provisional)


def test_direct_and_recursive_streaming_backends_match_without_noise() -> None:
    config = compact_waveform_config()
    raw = config.model_dump(mode="python")
    raw["baseline"]["enabled"] = False
    raw["noise"]["enabled"] = False
    noiseless = He3SimConfig.model_validate(raw)
    direct = prepare_waveform_simulation(
        noiseless,
        renderer_override=WaveformRenderer.DIRECT_SPARSE,
    )
    recursive = prepare_waveform_simulation(
        noiseless,
        renderer_override=WaveformRenderer.RECURSIVE_FIXED_TAU,
    )
    direct_samples = np.concatenate(
        [
            block.analog_samples_V
            for block in iter_waveform_blocks(direct, noiseless)
            if block.analog_samples_V is not None
        ]
    )
    recursive_samples = np.concatenate(
        [
            block.analog_samples_V
            for block in iter_waveform_blocks(recursive, noiseless)
            if block.analog_samples_V is not None
        ]
    )

    np.testing.assert_allclose(recursive_samples, direct_samples, rtol=2.0e-6, atol=2.0e-8)
    assert direct.true_events.events.size == recursive.true_events.events.size


def test_phase2_cli_simulate_and_inspect(tmp_path: Path) -> None:
    config_path = PROJECT_ROOT / "configs" / "demo_minimal.yaml"
    output_path = tmp_path / "phase02.h5"

    simulation = RUNNER.invoke(
        app,
        ["simulate-waveform", "-c", str(config_path), "-o", str(output_path)],
    )
    assert simulation.exit_code == 0, simulation.output
    assert "waveform samples" in simulation.output
    assert "renderer: recursive_fixed_tau" in simulation.output

    inspection = RUNNER.invoke(app, ["inspect", str(output_path)])
    assert inspection.exit_code == 0, inspection.output
    assert '"/blocks/adc_samples"' in inspection.output
    assert '"/events/true"' in inspection.output
