from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pytest
from matplotlib.figure import Figure

from he3sim.analysis.figures import (
    phase_a_chain_tree_figure,
    phase_a_degeneracy_figure,
    phase_a_event_raster_figure,
    phase_a_fano_figure,
    phase_a_interval_distribution_figure,
    phase_a_rate_sweep_figure,
)
from he3sim.analysis.phase_a_validation import (
    PhaseAValidationArtifacts,
    build_phase_a_validation,
    write_phase_a_validation_report,
)
from he3sim.config import He3SimConfig, load_config

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def phase_a_case() -> tuple[He3SimConfig, PhaseAValidationArtifacts]:
    config = load_config(PROJECT_ROOT / "configs" / "demo_minimal.yaml")
    return config, build_phase_a_validation(
        config,
        validation_events=2_000,
        rate_sweep_events=2_000,
    )


def test_phase_a_data_recovers_required_physical_and_statistical_limits(
    phase_a_case: tuple[He3SimConfig, PhaseAValidationArtifacts],
) -> None:
    _, artifacts = phase_a_case
    metrics = artifacts.metrics

    assert metrics.observed_correlated_rate_cps == pytest.approx(
        metrics.expected_rate_cps,
        rel=0.03,
    )
    assert metrics.maximum_rate_sweep_relative_error <= 0.05
    assert metrics.maximum_correlated_fano > 1.05
    assert metrics.degeneracy_ks_distance <= metrics.degeneracy_ks_tolerance
    assert artifacts.alpha_per_s == pytest.approx(1_000.0)
    assert metrics.passed


def test_phase_a_figure_functions_only_render_precomputed_inputs(
    phase_a_case: tuple[He3SimConfig, PhaseAValidationArtifacts],
) -> None:
    _, artifacts = phase_a_case
    metrics = artifacts.metrics
    figures = [
        phase_a_event_raster_figure(
            artifacts.poisson_raster_times_s,
            artifacts.correlated_raster_times_s,
            artifacts.raster_duration_s,
            metrics.expected_rate_cps,
            artifacts.k_eff,
            artifacts.alpha_per_s,
        ),
        phase_a_interval_distribution_figure(
            artifacts.interval_centers_s,
            artifacts.poisson_interval_density,
            artifacts.correlated_interval_density,
            artifacts.exponential_interval_density,
            metrics.expected_rate_cps,
            metrics.short_interval_excess,
        ),
        phase_a_fano_figure(
            artifacts.gate_widths_s,
            artifacts.poisson_fano,
            artifacts.correlated_fano,
            metrics.maximum_correlated_fano,
        ),
        phase_a_rate_sweep_figure(
            artifacts.k_eff_values,
            artifacts.observed_rates_cps,
            artifacts.analytic_rates_cps,
            metrics.maximum_rate_sweep_relative_error,
        ),
        phase_a_chain_tree_figure(artifacts.trace_nodes, artifacts.trace_chain_id),
        phase_a_degeneracy_figure(
            artifacts.degeneracy_interval_centers,
            artifacts.degeneracy_density,
            artifacts.degeneracy_exponential_density,
            metrics.degeneracy_k_eff,
            metrics.degeneracy_ks_distance,
        ),
    ]

    assert all(isinstance(figure, Figure) for figure in figures)
    assert all(len(figure.axes) == 1 for figure in figures)
    for figure in figures:
        plt.close(figure)


def test_phase_a_report_contains_six_png_offline_html_and_metrics(
    tmp_path: Path,
    phase_a_case: tuple[He3SimConfig, PhaseAValidationArtifacts],
) -> None:
    config, artifacts = phase_a_case
    report_path = write_phase_a_validation_report(tmp_path, config, artifacts)
    png_paths = sorted(tmp_path.glob("*.png"))

    assert len(png_paths) == 6
    assert all(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for path in png_paths)
    report = report_path.read_text(encoding="utf-8")
    assert "Technical summary: PASSED" in report
    assert "alpha=1000" in report
    assert "No interactive dashboard is included" in report
    assert "<script" not in report.lower()
    assert all(path.name in report for path in png_paths)
    payload = json.loads((tmp_path / "phase_a_validation.json").read_text(encoding="utf-8"))
    assert payload["result"] == "passed"
    assert payload["metrics"] == artifacts.metrics.to_dict()
