from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest

from he3sim.config import He3SimConfig, load_config
from he3sim.io.dataset import write_dataset_hdf5
from he3sim.physics.event_stream import StreamingTrueEventGenerator
from he3sim.synthesis.dataset import prepare_dataset_simulation

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def streaming_config() -> He3SimConfig:
    config = load_config(PROJECT_ROOT / "configs" / "demo_minimal.yaml")
    raw = config.model_dump(mode="python")
    raw["simulation"]["true_rate_cps"]["value"] = 1.0e7
    raw["simulation"]["sample_rate_hz"]["value"] = 100.0e6
    raw["observation"]["duration_s"]["value"] = 1.0e-3
    raw["dataset"]["continuous_duration_s"]["value"] = 1.0e-5
    raw["dataset"]["max_windows"]["value"] = 8
    raw["waveform"]["max_samples_per_block"]["value"] = 128
    raw["noise"]["enabled"] = False
    raw["baseline"]["enabled"] = False
    raw["trigger"]["threshold_V"]["value"] = 0.005
    raw["trigger"]["hysteresis_V"]["value"] = 0.001
    raw["trigger"]["min_hold_s"]["value"] = 0.0
    raw["trigger"]["pre_trigger_s"]["value"] = 2.0e-6
    raw["trigger"]["post_trigger_s"]["value"] = 5.0e-6
    raw["dead_time"]["duration_s"]["value"] = 1.0e-7
    return He3SimConfig.model_validate(raw)


def test_complete_dataset_is_streamed_traceable_and_reproducible(tmp_path: Path) -> None:
    config = streaming_config()
    left_plan = prepare_dataset_simulation(config, max_expected_events=20_000)
    right_plan = prepare_dataset_simulation(config, max_expected_events=20_000)
    left = write_dataset_hdf5(tmp_path / "left.h5", left_plan, config)
    right = write_dataset_hdf5(tmp_path / "right.h5", right_plan, config)

    with h5py.File(left, "r") as first, h5py.File(right, "r") as second:
        assert set(first) == {
            "blocks",
            "calibration",
            "events",
            "metadata",
            "statistics",
            "windows",
        }
        assert set(first["events"]) == {"observed", "trigger_event_links", "true"}
        assert set(first["windows"]) == {"adc", "metadata"}
        true_events = np.asarray(first["events/true"])
        observed = np.asarray(first["events/observed"])
        links = np.asarray(first["events/trigger_event_links"])
        rendered = true_events[true_events["block_id"] >= 0]
        assert true_events.size > rendered.size
        assert int(np.sum(first["blocks/index"]["event_count"])) == rendered.size
        assert np.all(true_events[true_events["block_id"] < 0]["sample_index"] == -1)
        assert np.all(links["trigger_id"] < observed.size)
        assert np.all(np.isin(links["event_id"], true_events["event_id"]))
        if links.size:
            assert np.max(np.bincount(links["trigger_id"])) > 1
        assert first["events/true"].compression == "gzip"
        assert first["blocks/adc_samples"].chunks[0] <= 128
        assert first["windows/adc"].shape[0] <= 8
        assert first["metadata"].attrs["event_horizon_s"] == 1.0e-3
        assert first["metadata"].attrs["continuous_duration_s"] == 1.0e-5
        for dataset_path in (
            "events/true",
            "events/trigger_event_links",
            "blocks/analog_samples",
            "blocks/adc_samples",
            "blocks/saturation_mask",
        ):
            np.testing.assert_array_equal(first[dataset_path], second[dataset_path])
        for field in observed.dtype.names or ():
            left_values = first["events/observed"][field]
            right_values = second["events/observed"][field]
            if np.issubdtype(left_values.dtype, np.floating):
                np.testing.assert_allclose(left_values, right_values, equal_nan=True)
            else:
                np.testing.assert_array_equal(left_values, right_values)


def test_dead_time_never_removes_truth_or_continuous_samples(tmp_path: Path) -> None:
    config = streaming_config()
    raw = config.model_dump(mode="python")
    raw["dead_time"]["duration_s"]["value"] = 5.0e-6
    config = He3SimConfig.model_validate(raw)
    plan = prepare_dataset_simulation(config, max_expected_events=20_000)
    output = write_dataset_hdf5(tmp_path / "deadtime.h5", plan, config)

    with h5py.File(output, "r") as handle:
        true_before_observation = np.asarray(handle["events/true"])
        observed = np.asarray(handle["events/observed"])
        assert true_before_observation.size == handle["statistics"].attrs["true_event_count"]
        assert handle["blocks/analog_samples"].shape[0] == plan.waveform.sample_count
        if observed.size > 1:
            assert np.any(~observed["accepted"])
            assert set(observed["rejection_reason"].tolist()) <= {b"none", b"dead_time"}


def test_truth_stream_has_an_explicit_per_chunk_memory_guard() -> None:
    config = streaming_config()
    generator = StreamingTrueEventGenerator(config, max_events=20_000, max_chunk_events=1)

    with pytest.raises(ValueError, match="chunk limit"):
        generator.sample_interval(0.0, 1.0e-5)
