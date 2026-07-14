from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch
from typer.testing import CliRunner

from he3sim.cli import app
from he3sim.config import load_config
from he3sim.ml.config import (
    EventModelArchitectureConfig,
    EventModelEvaluationConfig,
    EventModelTrainingConfig,
    MLDevice,
    load_event_model_evaluation_config,
    load_event_model_training_config,
)
from he3sim.ml.data import (
    ExactPhysicsWindowSampler,
    collate_event_windows,
    detector_specification,
    generate_log_uniform_windows,
)
from he3sim.ml.evaluation import compare_event_model
from he3sim.ml.event_model import ConditionalMarkedEventModel
from he3sim.ml.training import (
    load_event_model_checkpoint,
    resolve_torch_device,
    train_event_model,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_CONFIG = PROJECT_ROOT / "configs" / "demo_minimal.yaml"


def _small_training_config(output_directory: Path) -> EventModelTrainingConfig:
    return EventModelTrainingConfig(
        base_config_path=BASE_CONFIG,
        output_directory=output_directory,
        device=MLDevice.CPU,
        seed=20260714,
        train_windows=16,
        validation_windows=13,
        epochs=2,
        batch_size=8,
        learning_rate=1.0e-3,
        checkpoint_every=1,
        expected_events_min=4.0,
        expected_events_max=8.0,
        max_events_per_window=64,
        architecture=EventModelArchitectureConfig(
            hidden_dim=16,
            hidden_layers=1,
            interval_mixture_components=2,
            minimum_scale=0.02,
        ),
    )


def test_ml_yaml_paths_resolve_relative_to_config_directory() -> None:
    training = load_event_model_training_config(PROJECT_ROOT / "configs" / "ml_event.yaml")
    evaluation = load_event_model_evaluation_config(PROJECT_ROOT / "configs" / "ml_event_eval.yaml")

    assert training.base_config_path == BASE_CONFIG
    assert training.output_directory == PROJECT_ROOT / "outputs" / "phase05_training"
    assert evaluation.base_config_path == BASE_CONFIG
    assert evaluation.checkpoint_path == (
        PROJECT_ROOT / "outputs" / "phase05_training" / "checkpoint_latest.pt"
    )


def test_model_generates_reproducible_ordered_legal_variable_events() -> None:
    base_config = load_config(BASE_CONFIG)
    model = ConditionalMarkedEventModel(
        EventModelArchitectureConfig(hidden_dim=16, hidden_layers=1),
        detector_specification(base_config),
    )

    first = model.generate(100_000.0, 3.2e-4, seed=77, max_events=128)
    second = model.generate(100_000.0, 3.2e-4, seed=77, max_events=128)

    np.testing.assert_array_equal(first, second)
    assert first.size != 32
    assert np.all(np.diff(first["t_s"]) > 0.0)
    assert np.all((first["t_s"] >= 0.0) & (first["t_s"] < 3.2e-4))
    assert np.all(first["energy_dep_keV"] >= 0.0)
    assert np.all(first["amplitude_peak_V"] > 0.0)
    assert np.all(first["tau_r_s"] > 0.0)
    assert np.all(first["tau_d_s"] > first["tau_r_s"])
    assert set(np.unique(first["spectrum_component_id"])).issubset({0, 1, 2, 3})
    assert set(np.unique(first["parameter_status"])) == {b"synthetic_demo"}


def test_all_heads_use_finite_likelihood_and_support_one_training_step() -> None:
    base_config = load_config(BASE_CONFIG)
    detector = detector_specification(base_config)
    model = ConditionalMarkedEventModel(
        EventModelArchitectureConfig(hidden_dim=16, hidden_layers=1), detector
    )
    sampler = ExactPhysicsWindowSampler(base_config)
    windows = generate_log_uniform_windows(
        sampler,
        count=8,
        rate_min_cps=10.0,
        rate_max_cps=1.0e7,
        expected_events_min=4.0,
        expected_events_max=8.0,
        max_events=64,
        seed=123,
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=1.0e-3)

    losses = model.negative_log_likelihood(collate_event_windows(windows))
    assert set(losses) == {
        "total",
        "count",
        "interval",
        "event_type",
        "energy",
        "amplitude",
        "tau",
    }
    assert all(torch.isfinite(loss) for loss in losses.values())
    optimizer.zero_grad(set_to_none=True)
    losses["total"].backward()
    optimizer.step()
    assert any(parameter.grad is not None for parameter in model.parameters())


def test_cpu_training_checkpoint_model_card_and_comparison(tmp_path: Path) -> None:
    training = _small_training_config(tmp_path / "training")
    artifacts = train_event_model(training)

    assert artifacts.device == "cpu"
    assert artifacts.epochs_completed == 2
    assert artifacts.checkpoint_path.is_file()
    assert artifacts.model_card_path.is_file()
    summary = json.loads(artifacts.summary_path.read_text(encoding="utf-8"))
    assert summary["model_status"] == "experimental"
    assert summary["default_generator"] == "exact_poisson_parametric_spectrum"
    model, payload = load_event_model_checkpoint(artifacts.checkpoint_path, torch.device("cpu"))
    assert model.model_status == "experimental"
    assert payload["epoch"] == 2

    resumed = training.model_copy(update={"resume_from": artifacts.checkpoint_path, "epochs": 3})
    resumed_artifacts = train_event_model(resumed)
    _, resumed_payload = load_event_model_checkpoint(
        resumed_artifacts.checkpoint_path, torch.device("cpu")
    )
    assert resumed_payload["epoch"] == 3

    evaluation = EventModelEvaluationConfig(
        base_config_path=BASE_CONFIG,
        checkpoint_path=artifacts.checkpoint_path,
        device=MLDevice.CPU,
        seed=20260715,
        replicates_per_rate=8,
        expected_events_per_window=4.0,
        max_events_per_window=64,
        standard_rates_cps=(10.0,),
        interpolation_rates_cps=(17.32050807568877,),
    )
    comparison = compare_event_model(evaluation, tmp_path / "comparison")
    assert comparison.model_status == "experimental"
    assert comparison.report_path.is_file()
    payload = json.loads(comparison.json_path.read_text(encoding="utf-8"))
    assert payload["promotion_recommended"] is False
    assert payload["default_generator"] == "exact_poisson_parametric_spectrum"
    assert len(payload["comparisons"]) == 2
    assert all(item["illegal_event_count"] == 0 for item in payload["comparisons"])


def test_cuda_request_never_silently_falls_back() -> None:
    if torch.cuda.is_available():
        assert resolve_torch_device(MLDevice.CUDA).type == "cuda"
    else:
        with pytest.raises(RuntimeError, match="CUDA was requested"):
            resolve_torch_device(MLDevice.CUDA)


@pytest.mark.parametrize("command", ["train-event-model", "compare-event-model"])
def test_phase5_cli_help_is_available(command: str) -> None:
    result = CliRunner().invoke(app, [command, "--help"])

    assert result.exit_code == 0, result.output
    assert "Phase 5" in result.output
