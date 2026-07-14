"""Command-line interface through the experimental Phase 5 research model."""

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
from he3sim.analysis.reports import write_arrival_validation_report
from he3sim.analysis.waveform_plot import (
    DEFAULT_MAX_OVERVIEW_POINTS,
    plot_waveform_hdf5,
)
from he3sim.config import WaveformRenderer, config_hash, load_config
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
    help="He-3 physical simulation, local Web, and experimental Phase 5 research tools.",
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
) -> None:
    """Generate and persist truth events without rendering a waveform."""
    try:
        config = load_config(config_path)
        simulation = simulate_true_events(
            config,
            algorithm=algorithm,
            max_expected_events=max_expected_events,
        )
        written_path = write_true_events_hdf5(output_path, simulation, config)
    except (OSError, ValueError, RuntimeError, yaml.YAMLError, ValidationError) as exc:
        typer.echo(f"event simulation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"wrote {simulation.events.size} truth events: {written_path}")
    typer.echo(f"arrival_algorithm: {simulation.arrival_algorithm.value}")
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


@app.command("web")
def web_command(
    port: Annotated[
        int,
        typer.Option(help="Loopback TCP port for the local Streamlit server."),
    ] = 8501,
    headless: Annotated[
        bool,
        typer.Option(help="Do not ask Streamlit to open a browser automatically."),
    ] = False,
) -> None:
    """Launch the Phase 3.5 interface on 127.0.0.1 only."""
    from he3sim.app.launcher import launch_local_web

    try:
        launch_local_web(port=port, headless=headless)
    except ValueError as exc:
        typer.echo(f"local Web launch failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc


@app.command("train-event-model")
def train_event_model_command(
    config_path: Annotated[
        Path,
        typer.Option("--config", "-c", help="Phase 5 event-model training YAML."),
    ],
) -> None:
    """Train and checkpoint experimental network A with likelihood objectives."""
    try:
        from he3sim.ml.config import load_event_model_training_config
        from he3sim.ml.training import train_event_model

        artifacts = train_event_model(load_event_model_training_config(config_path))
    except ImportError as exc:
        typer.echo("Phase 5 requires the optional 'ml' dependencies", err=True)
        raise typer.Exit(code=2) from exc
    except (OSError, ValueError, RuntimeError, yaml.YAMLError, ValidationError) as exc:
        typer.echo(f"event-model training failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"checkpoint: {artifacts.checkpoint_path}")
    typer.echo(f"model_card: {artifacts.model_card_path}")
    typer.echo(f"training_summary: {artifacts.summary_path}")
    typer.echo(f"device: {artifacts.device}")
    typer.echo("model_status: experimental")
    typer.echo("default_generator: exact_poisson_parametric_spectrum")


@app.command("compare-event-model")
def compare_event_model_command(
    config_path: Annotated[
        Path,
        typer.Option("--config", "-c", help="Phase 5 evaluation YAML."),
    ],
    output_directory: Annotated[
        Path,
        typer.Option("--output", "-o", help="Directory for comparison reports."),
    ],
) -> None:
    """Compare experimental network A with the exact physical baseline."""
    try:
        from he3sim.ml.config import load_event_model_evaluation_config
        from he3sim.ml.evaluation import compare_event_model

        artifacts = compare_event_model(
            load_event_model_evaluation_config(config_path), output_directory
        )
    except ImportError as exc:
        typer.echo("Phase 5 requires the optional 'ml' dependencies", err=True)
        raise typer.Exit(code=2) from exc
    except (OSError, ValueError, RuntimeError, yaml.YAMLError, ValidationError) as exc:
        typer.echo(f"event-model comparison failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"comparison_report: {artifacts.report_path}")
    typer.echo(f"statistical_match: {str(artifacts.statistical_match).lower()}")
    typer.echo(f"model_status: {artifacts.model_status}")
    typer.echo("default_generator: exact_poisson_parametric_spectrum")


def main() -> None:
    """Run the Typer application."""
    app()
