from __future__ import annotations

from pathlib import Path

import matplotlib.image as mpimg
import numpy as np
from typer.testing import CliRunner

from he3sim.analysis.waveform_plot import (
    MAX_DETAIL_EVENT_MARKERS,
    _adaptive_y_limits,
    plot_waveform_hdf5,
)
from he3sim.cli import app
from he3sim.config import He3SimConfig, load_config
from he3sim.io.hdf5 import write_waveform_hdf5
from he3sim.synthesis.streaming import prepare_waveform_simulation

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER = CliRunner()


def write_compact_waveform(tmp_path: Path) -> tuple[Path, int]:
    config = load_config(PROJECT_ROOT / "configs" / "demo_minimal.yaml")
    raw = config.model_dump(mode="python")
    raw["simulation"]["true_rate_cps"]["value"] = 1.0e7
    raw["simulation"]["sample_rate_hz"]["value"] = 100.0e6
    raw["observation"]["duration_s"]["value"] = 20.0e-6
    raw["waveform"]["max_samples_per_block"]["value"] = 64
    compact = He3SimConfig.model_validate(raw)
    simulation = prepare_waveform_simulation(compact)
    input_path = write_waveform_hdf5(tmp_path / "waveform.h5", simulation, compact)
    return input_path, int(simulation.true_events.events.size)


def test_waveform_plot_exports_readable_three_panel_png(tmp_path: Path) -> None:
    input_path, event_count = write_compact_waveform(tmp_path)
    output_path = tmp_path / "waveform.png"

    summary = plot_waveform_hdf5(input_path, output_path, max_overview_points=200)

    assert summary.output_path == output_path
    assert summary.event_count == event_count
    assert summary.selected_event_id is not None
    assert summary.parameter_status == "synthetic_demo"
    assert summary.nearby_event_count >= summary.plotted_event_marker_count
    assert summary.plotted_event_marker_count <= MAX_DETAIL_EVENT_MARKERS
    assert 0.0 <= summary.focus_saturation_fraction <= 1.0
    assert output_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    image = mpimg.imread(output_path)
    assert image.shape[0] >= 1_000
    assert image.shape[1] >= 1_500


def test_adaptive_y_limits_add_padding_for_constant_saturated_signal() -> None:
    lower, upper = _adaptive_y_limits(
        np.ones(2_000, dtype=np.float64),
        minimum_padding=1.0e-3,
    )

    assert lower < 1.0 < upper
    assert upper - lower >= 2.0e-3


def test_plot_waveform_cli_reports_selected_event(tmp_path: Path) -> None:
    input_path, event_count = write_compact_waveform(tmp_path)
    output_path = tmp_path / "cli_waveform.png"

    result = RUNNER.invoke(
        app,
        ["plot-waveform", str(input_path), "-o", str(output_path)],
    )

    assert result.exit_code == 0, result.output
    assert output_path.exists()
    assert f"truth_events: {event_count}" in result.output
    assert "selected_event_id:" in result.output
    assert "parameter_status: synthetic_demo" in result.output


def test_waveform_plot_rejects_non_png_output(tmp_path: Path) -> None:
    input_path, _ = write_compact_waveform(tmp_path)

    result = RUNNER.invoke(
        app,
        ["plot-waveform", str(input_path), "-o", str(tmp_path / "waveform.svg")],
    )

    assert result.exit_code == 2
    assert "must use the .png extension" in result.output
