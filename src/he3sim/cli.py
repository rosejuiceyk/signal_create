"""Command-line interface for physical simulation and read-only data qualification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
import yaml
from pydantic import ValidationError

from he3sim.analysis.counting_stats import validate_arrival_algorithms
from he3sim.analysis.phase3_validation import (
    validate_phase3_physics,
    write_phase3_validation_report,
)
from he3sim.analysis.phase_a_validation import (
    DEFAULT_RATE_SWEEP_EVENTS,
    DEFAULT_VALIDATION_EVENTS,
    build_phase_a_validation,
    write_phase_a_validation_report,
)
from he3sim.analysis.reports import write_arrival_validation_report
from he3sim.analysis.waveform_plot import (
    DEFAULT_MAX_OVERVIEW_POINTS,
    plot_waveform_hdf5,
)
from he3sim.calibration.qualification import qualify_acquisition
from he3sim.config import SourceModelKind, WaveformRenderer, config_hash, load_config
from he3sim.io.dataset import write_dataset_hdf5
from he3sim.io.hdf5 import inspect_hdf5, write_true_events_hdf5, write_waveform_hdf5
from he3sim.physics.arrivals import ArrivalAlgorithm
from he3sim.physics.events import (
    DEFAULT_MAX_EXPECTED_EVENTS,
    resolve_duration_s,
    simulate_true_events,
)
from he3sim.synthesis.dataset import prepare_dataset_simulation
from he3sim.synthesis.streaming import (
    DEFAULT_MAX_WAVEFORM_SAMPLES,
    prepare_waveform_simulation,
)

app = typer.Typer(
    name="he3sim",
    help="He-3 physical simulation and read-only acquisition qualification tools.",
    no_args_is_help=True,
)


@app.callback()
def root_command() -> None:
    """Expose Phase 0 commands under the stable ``he3sim`` command group."""


@app.command("validate-config")
def validate_config_command(
    config_path: Annotated[
        Path,
        typer.Option("--config", "-c", help="YAML configuration to validate."),
    ],
) -> None:
    """Validate one YAML configuration and print its deterministic hash."""
    try:
        config = load_config(config_path)
    except (OSError, ValueError, yaml.YAMLError, ValidationError) as exc:
        typer.echo(f"invalid configuration: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"valid configuration: {config_path}")
    typer.echo(f"config_hash: {config_hash(config)}")


@app.command("simulate-events")
def simulate_events_command(
    config_path: Annotated[
        Path,
        typer.Option("--config", "-c", help="YAML configuration to use."),
    ],
    output_path: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output Phase 1 HDF5 event file."),
    ],
    algorithm: Annotated[
        ArrivalAlgorithm,
        typer.Option(help="Exact homogeneous-Poisson sampling algorithm."),
    ] = ArrivalAlgorithm.POISSON_UNIFORM,
    max_expected_events: Annotated[
        int,
        typer.Option(help="Explicit in-memory safety limit for expected events."),
    ] = DEFAULT_MAX_EXPECTED_EVENTS,
    source_model: Annotated[
        SourceModelKind | None,
        typer.Option(
            "--source-model",
            help="Optional truth-arrival source override; defaults to the configuration.",
        ),
    ] = None,
) -> None:
    """Generate and persist truth events without rendering a waveform."""
    try:
        config = load_config(config_path)
        simulation = simulate_true_events(
            config,
            algorithm=algorithm,
            max_expected_events=max_expected_events,
            source_model=source_model,
        )
        written_path = write_true_events_hdf5(output_path, simulation, config)
    except (OSError, ValueError, RuntimeError, yaml.YAMLError, ValidationError) as exc:
        typer.echo(f"event simulation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"wrote {simulation.events.size} truth events: {written_path}")
    typer.echo(f"arrival_algorithm: {simulation.arrival_algorithm.value}")
    typer.echo(f"source_model: {simulation.source_model.value}")
    typer.echo(f"config_hash: {config_hash(config)}")


@app.command("validate-arrivals")
def validate_arrivals_command(
    config_path: Annotated[
        Path,
        typer.Option("--config", "-c", help="YAML configuration to validate."),
    ],
    output_directory: Annotated[
        Path,
        typer.Option("--output", "-o", help="Directory for reports and figures."),
    ],
    replicates: Annotated[
        int,
        typer.Option(help="Fixed-seed replicate count; must be at least 30."),
    ] = 500,
) -> None:
    """Validate both exact arrival algorithms and write deterministic diagnostics."""
    try:
        config = load_config(config_path)
        if config.simulation.true_rate_cps.value is None:
            raise ValueError("true_rate_cps requires an explicit value")
        if config.metadata.seed.value is None:
            raise ValueError("seed requires an explicit value")
        artifacts = validate_arrival_algorithms(
            true_rate_cps=config.simulation.true_rate_cps.value,
            configured_duration_s=resolve_duration_s(config),
            seed=config.metadata.seed.value,
            replicates=replicates,
        )
        report_path = write_arrival_validation_report(output_directory, artifacts)
    except (OSError, ValueError, RuntimeError, yaml.YAMLError, ValidationError) as exc:
        typer.echo(f"arrival validation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"arrival validation report: {report_path}")
    typer.echo(f"result: {'passed' if artifacts.report.passed else 'failed'}")
    if not artifacts.report.passed:
        raise typer.Exit(code=3)


@app.command("validate-correlated")
def validate_correlated_command(
    config_path: Annotated[
        Path,
        typer.Option("--config", "-c", help="YAML configuration with Phase A parameters."),
    ],
    output_directory: Annotated[
        Path,
        typer.Option("--output", "-o", help="Directory for Phase A PNG and HTML reports."),
    ] = Path("outputs/phaseA_report"),
    validation_events: Annotated[
        int,
        typer.Option(help="Expected event count for interval, Fano, and degeneracy views."),
    ] = DEFAULT_VALIDATION_EVENTS,
    rate_sweep_events: Annotated[
        int,
        typer.Option(help="Expected events at each k_eff point in the mean-rate sweep."),
    ] = DEFAULT_RATE_SWEEP_EVENTS,
) -> None:
    """Generate the Phase A quantitative PNG and offline HTML validation report."""
    try:
        config = load_config(config_path)
        artifacts = build_phase_a_validation(
            config,
            validation_events=validation_events,
            rate_sweep_events=rate_sweep_events,
        )
        report_path = write_phase_a_validation_report(output_directory, config, artifacts)
    except (OSError, ValueError, RuntimeError, yaml.YAMLError, ValidationError) as exc:
        typer.echo(f"Phase A validation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Phase A validation report: {report_path}")
    typer.echo("figures: 6 PNG")
    typer.echo(
        f"observed_rate_relative_error: {artifacts.metrics.observed_rate_relative_error:.6g}"
    )
    typer.echo(f"maximum_correlated_fano: {artifacts.metrics.maximum_correlated_fano:.6g}")
    typer.echo(
        "maximum_rate_sweep_relative_error: "
        f"{artifacts.metrics.maximum_rate_sweep_relative_error:.6g}"
    )
    typer.echo(f"degeneracy_ks_distance: {artifacts.metrics.degeneracy_ks_distance:.6g}")
    typer.echo(f"result: {'passed' if artifacts.metrics.passed else 'failed'}")
    if not artifacts.metrics.passed:
        raise typer.Exit(code=3)


@app.command("simulate-waveform")
def simulate_waveform_command(
    config_path: Annotated[
        Path,
        typer.Option("--config", "-c", help="YAML configuration to use."),
    ],
    output_path: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output Phase 2 HDF5 waveform file."),
    ],
    algorithm: Annotated[
        ArrivalAlgorithm,
        typer.Option(help="Exact homogeneous-Poisson arrival algorithm."),
    ] = ArrivalAlgorithm.POISSON_UNIFORM,
    renderer: Annotated[
        WaveformRenderer | None,
        typer.Option(help="Optional rendering-backend override."),
    ] = None,
    max_expected_events: Annotated[
        int,
        typer.Option(help="Explicit in-memory safety limit for expected truth events."),
    ] = DEFAULT_MAX_EXPECTED_EVENTS,
    max_waveform_samples: Annotated[
        int,
        typer.Option(help="Explicit upper bound for the continuous sample grid."),
    ] = DEFAULT_MAX_WAVEFORM_SAMPLES,
) -> None:
    """Generate all truth events and stream their continuous/ADC waveform blocks."""
    try:
        config = load_config(config_path)
        simulation = prepare_waveform_simulation(
            config,
            algorithm=algorithm,
            max_expected_events=max_expected_events,
            max_waveform_samples=max_waveform_samples,
            renderer_override=renderer,
        )
        written_path = write_waveform_hdf5(output_path, simulation, config)
    except (OSError, ValueError, RuntimeError, yaml.YAMLError, ValidationError) as exc:
        typer.echo(f"waveform simulation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"wrote {simulation.sample_count} waveform samples: {written_path}")
    typer.echo(f"truth_events: {simulation.true_events.events.size}")
    typer.echo(f"renderer: {simulation.renderer.value}")
    typer.echo(f"config_hash: {config_hash(config)}")


@app.command("inspect")
def inspect_command(
    input_path: Annotated[
        Path, typer.Argument(help="HDF5 file to inspect without loading arrays.")
    ],
) -> None:
    """Print a JSON summary of HDF5 groups, datasets, shapes, and metadata."""
    try:
        summary = inspect_hdf5(input_path)
    except (OSError, ValueError) as exc:
        typer.echo(f"inspection failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


@app.command("plot-waveform")
def plot_waveform_command(
    input_path: Annotated[Path, typer.Argument(help="Phase 2 waveform HDF5 file.")],
    output_path: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output PNG review image."),
    ],
    event_id: Annotated[
        int | None,
        typer.Option(help="Truth event ID to center; defaults to the largest pulse."),
    ] = None,
    max_overview_points: Annotated[
        int,
        typer.Option(help="Maximum min/max-envelope bins in the overview."),
    ] = DEFAULT_MAX_OVERVIEW_POINTS,
) -> None:
    """Create a read-only overview and event-detail PNG from Phase 2 HDF5."""
    try:
        summary = plot_waveform_hdf5(
            input_path,
            output_path,
            event_id=event_id,
            max_overview_points=max_overview_points,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        typer.echo(f"waveform plotting failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"waveform plot: {summary.output_path}")
    typer.echo(f"samples: {summary.sample_count}")
    typer.echo(f"truth_events: {summary.event_count}")
    typer.echo(
        "selected_event_id: "
        f"{summary.selected_event_id if summary.selected_event_id is not None else 'none'}"
    )
    typer.echo(f"parameter_status: {summary.parameter_status}")


@app.command("generate-dataset")
def generate_dataset_command(
    config_path: Annotated[
        Path,
        typer.Option("--config", "-c", help="YAML configuration to use."),
    ],
    output_path: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output HDF5 file or dataset directory."),
    ],
    max_expected_events: Annotated[
        int,
        typer.Option(help="Explicit total truth-event safety limit."),
    ] = DEFAULT_MAX_EXPECTED_EVENTS,
    max_waveform_samples: Annotated[
        int,
        typer.Option(help="Explicit continuous-region sample safety limit."),
    ] = DEFAULT_MAX_WAVEFORM_SAMPLES,
) -> None:
    """Stream a complete Phase 3 truth, waveform, observation, and window dataset."""
    try:
        config = load_config(config_path)
        simulation = prepare_dataset_simulation(
            config,
            max_expected_events=max_expected_events,
            max_waveform_samples=max_waveform_samples,
        )
        written_path = write_dataset_hdf5(output_path, simulation, config)
        summary = inspect_hdf5(written_path)
    except (OSError, ValueError, RuntimeError, yaml.YAMLError, ValidationError) as exc:
        typer.echo(f"dataset generation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    metadata = summary["/metadata"]["attributes"]
    statistics = summary["/statistics"]["attributes"]
    typer.echo(f"dataset: {written_path}")
    typer.echo(f"truth_events: {statistics['true_event_count']}")
    typer.echo(f"rendered_truth_events: {statistics['rendered_true_event_count']}")
    typer.echo(f"accepted_triggers: {statistics['accepted_trigger_count']}")
    typer.echo(f"event_horizon_s: {metadata['event_horizon_s']}")
    typer.echo(f"continuous_duration_s: {metadata['continuous_duration_s']}")
    typer.echo(f"config_hash: {metadata['config_hash']}")


@app.command("validate-physics")
def validate_physics_command(
    config_path: Annotated[
        Path,
        typer.Option("--config", "-c", help="YAML configuration to validate."),
    ],
    output_directory: Annotated[
        Path,
        typer.Option("--output", "-o", help="Directory for Phase 3 reports."),
    ],
    replicates: Annotated[
        int,
        typer.Option(help="Replicates at each of the thirteen standard rates."),
    ] = 60,
) -> None:
    """Validate ideal dead-time formulas and bounded streaming-memory controls."""
    try:
        config = load_config(config_path)
        report = validate_phase3_physics(config, replicates=replicates)
        report_path = write_phase3_validation_report(output_directory, report)
    except (OSError, ValueError, RuntimeError, yaml.YAMLError, ValidationError) as exc:
        typer.echo(f"Phase 3 validation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Phase 3 validation report: {report_path}")
    typer.echo(f"standard_rates: {len({point.true_rate_cps for point in report.points})}")
    typer.echo(f"result: {'passed' if report.passed else 'failed'}")
    if not report.passed:
        raise typer.Exit(code=3)


@app.command("qualify-acquisition")
def qualify_acquisition_command(
    input_root: Annotated[
        Path,
        typer.Option("--input", help="Read-only root containing acquisition run directories."),
    ],
    profile_path: Annotated[
        Path,
        typer.Option("--profile", help="Explicit Phase 4Q acquisition profile YAML."),
    ],
    output_directory: Annotated[
        Path,
        typer.Option("--output", "-o", help="Repository output directory for QC artifacts."),
    ],
    max_events_per_run: Annotated[
        int,
        typer.Option(
            help="Bounded event rows per run; use 0 only for an intentional full streaming scan."
        ),
    ] = 256,
) -> None:
    """Run read-only Phase 4Q hashing, event QC, and split-feasibility analysis."""
    try:
        artifacts = qualify_acquisition(
            input_root,
            profile_path,
            output_directory,
            max_events_per_run=None if max_events_per_run == 0 else max_events_per_run,
        )
    except (OSError, ValueError, RuntimeError, yaml.YAMLError, ValidationError) as exc:
        typer.echo(f"Phase 4Q qualification failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"output_directory: {artifacts.output_directory}")
    typer.echo(f"runs: {artifacts.run_count}")
    typer.echo(f"signal_runs: {artifacts.signal_run_count}")
    typer.echo(f"processed_events: {artifacts.processed_event_count}")
    typer.echo(f"scan_complete_runs: {artifacts.scan_complete_run_count}")
    typer.echo(f"scientific_exit_blocked: {str(artifacts.scientific_exit_blocked).lower()}")


def main() -> None:
    """Run the Typer application."""
    app()
