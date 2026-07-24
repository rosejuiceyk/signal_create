from __future__ import annotations

import json
from pathlib import Path

import h5py  # type: ignore[import-untyped]
import numpy as np
import pytest

from he3sim.app.web_backend import (
    InteractiveWaveformRequest,
    estimate_waveform_resources,
    generate_interactive_waveform,
    maximum_interactive_duration,
    read_sample_rows,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_CONFIG = PROJECT_ROOT / "configs" / "demo_minimal.yaml"


def _small_request() -> InteractiveWaveformRequest:
    return InteractiveWaveformRequest(
        true_rate_cps=100_000.0,
        sample_rate_hz=100.0e6,
        duration_s=10.0e-6,
        seed=20260711,
    )


def test_resource_estimate_has_explicit_units_and_limits() -> None:
    estimate = estimate_waveform_resources(_small_request())

    assert estimate.expected_event_count == pytest.approx(1.0)
    assert estimate.sample_count == 1_002
    assert estimate.sample_interval_s == pytest.approx(10.0e-9)
    assert estimate.estimated_waveform_payload_bytes == 1_002 * 11

    with pytest.raises(ValueError, match="采样点数"):
        estimate_waveform_resources(
            InteractiveWaveformRequest(
                true_rate_cps=10.0,
                sample_rate_hz=250.0e6,
                duration_s=1.0,
                seed=0,
            )
        )
    with pytest.raises(ValueError, match="true_rate_cps"):
        estimate_waveform_resources(InteractiveWaveformRequest(9.0, 100.0e6, 1.0e-6, 0))


def test_maximum_duration_combines_sample_and_event_guards() -> None:
    sample_limited = maximum_interactive_duration(1.0e7, 100.0e6)

    assert sample_limited.maximum_duration_s < 0.05
    assert sample_limited.maximum_duration_s == sample_limited.sample_limited_duration_s
    assert sample_limited.event_limited_duration_s == pytest.approx(0.1)
    assert sample_limited.limiting_constraint == "sample_count"

    event_limited = maximum_interactive_duration(
        1.0e7,
        100.0e6,
        max_expected_events=100,
    )
    assert event_limited.maximum_duration_s == pytest.approx(10.0e-6)
    assert event_limited.limiting_constraint == "expected_event_count"


def test_web_backend_writes_consistent_reproducible_artifacts(tmp_path: Path) -> None:
    original_config = BASE_CONFIG.read_bytes()
    first = generate_interactive_waveform(
        _small_request(),
        base_config_path=BASE_CONFIG,
        output_root=tmp_path / "first",
    )
    second = generate_interactive_waveform(
        _small_request(),
        base_config_path=BASE_CONFIG,
        output_root=tmp_path / "second",
    )

    for result in (first, second):
        assert result.config_path.is_file()
        assert result.waveform_path.is_file()
        assert result.csv_path.is_file()
        assert result.image_path.is_file()
        assert result.sampling_info_path.is_file()
        info = json.loads(result.sampling_info_path.read_text(encoding="utf-8"))
        assert info["sampling"]["sample_count"] == 1_002
        assert info["sampling"]["sample_interval_s"] == pytest.approx(10.0e-9)
        assert info["inputs"]["seed"] == 20260711
        assert info["provenance"]["config_hash"] == result.config_hash
        assert info["provenance"]["parameter_status"] == "synthetic_demo"
        assert info["events"]["actual_count"] == result.actual_event_count
        assert info["artifacts"]["waveform_csv"] == "waveform.csv"
        assert info["resources"]["waveform_csv_bytes"] == result.csv_path.stat().st_size

    with (
        h5py.File(first.waveform_path, "r") as first_h5,
        h5py.File(second.waveform_path, "r") as second_h5,
    ):
        assert np.array_equal(first_h5["events/true"][:], second_h5["events/true"][:])
        assert np.array_equal(
            first_h5["blocks/analog_samples"][:],
            second_h5["blocks/analog_samples"][:],
        )
        assert np.array_equal(
            first_h5["blocks/preclip_analog_samples"][:],
            second_h5["blocks/preclip_analog_samples"][:],
        )
        assert np.array_equal(
            first_h5["blocks/adc_samples"][:],
            second_h5["blocks/adc_samples"][:],
        )
        assert int(first_h5["metadata"].attrs["sample_count"]) == 1_002

        first_csv = np.loadtxt(
            first.csv_path,
            delimiter=",",
            skiprows=1,
            dtype=np.float64,
        )
        assert first_csv.shape == (1_002, 2)
        assert first.csv_path.read_text(encoding="utf-8").splitlines()[0] == ("time_s,voltage_V")
        assert np.array_equal(
            first_csv[:, 0],
            np.arange(1_002, dtype=np.float64) / 100.0e6,
        )
        assert np.array_equal(
            first_csv[:, 1].astype(np.float32),
            first_h5["blocks/analog_samples"][:],
        )

    rows = read_sample_rows(first.waveform_path, row_count=5)
    assert [row["sample_index"] for row in rows] == list(range(5))
    assert rows[1]["t_s"] == pytest.approx(10.0e-9)
    assert BASE_CONFIG.read_bytes() == original_config


def test_sample_preview_is_bounded(tmp_path: Path) -> None:
    result = generate_interactive_waveform(
        _small_request(),
        base_config_path=BASE_CONFIG,
        output_root=tmp_path,
    )
    with pytest.raises(ValueError, match="row_count"):
        read_sample_rows(result.waveform_path, row_count=1_001)
