from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch

from he3sim.ml.residual_config import (
    DeviceMode,
    SyntheticResidualRehearsalConfig,
    load_synthetic_residual_config,
    synthetic_residual_config_hash,
)
from he3sim.ml.residual_data import build_synthetic_residual_dataset
from he3sim.ml.residual_model import EventProtectedResidualTCN, normalized_condition
from he3sim.ml.residual_rehearsal import resolve_device, run_synthetic_residual_rehearsal
from he3sim.ml.residual_safety import apply_residual_with_guard

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs" / "ml_residual_synthetic.yaml"


def compact_config(*, epochs: int = 1) -> SyntheticResidualRehearsalConfig:
    config = load_synthetic_residual_config(CONFIG_PATH)
    payload = config.model_dump(mode="python")
    payload["true_rates_cps"] = [1.0e5, 1.0e6]
    payload["patch_samples"] = 256
    payload["model"]["hidden_channels"] = 4
    payload["model"]["dilations"] = [1, 2]
    payload["training"]["device"] = "cpu"
    payload["training"]["epochs"] = epochs
    payload["training"]["batch_size"] = 2
    payload["training"]["train_runs_per_rate"] = 2
    payload["training"]["validation_runs_per_rate"] = 1
    payload["training"]["test_runs_per_rate"] = 1
    return SyntheticResidualRehearsalConfig.model_validate(payload)


def test_synthetic_dataset_reuses_physics_and_keeps_splits_independent() -> None:
    config = compact_config()
    first = build_synthetic_residual_dataset(config)
    second = build_synthetic_residual_dataset(config)

    run_ids = [patch.run_id for patches in first.values() for patch in patches]
    assert len(run_ids) == len(set(run_ids))
    assert {patch.split for patch in first["train"]} == {"train"}
    np.testing.assert_array_equal(
        first["test"][0].physical_waveform_V,
        second["test"][0].physical_waveform_V,
    )
    np.testing.assert_array_equal(
        first["test"][0].artificial_residual_V,
        second["test"][0].artificial_residual_V,
    )
    for patch in first["train"]:
        assert patch.physical_waveform_V.shape == (config.patch_samples,)
        assert np.all(patch.artificial_residual_V[patch.event_guard_mask] == 0.0)


def test_rehearsal_hash_depends_on_physical_content_not_local_path(tmp_path: Path) -> None:
    config = compact_config()
    copied_physics = tmp_path / "renamed_physics.yaml"
    copied_physics.write_bytes(config.physical_config_path.read_bytes())
    moved = config.model_copy(update={"physical_config_path": copied_physics})

    assert synthetic_residual_config_hash(moved) == synthetic_residual_config_hash(config)


def test_tcn_residual_is_bounded_and_zero_on_event_guards() -> None:
    config = compact_config()
    model = EventProtectedResidualTCN(
        config.model,
        config.interference.max_abs_residual_V,
    )
    physical = torch.randn(2, 1, config.patch_samples) * 0.01
    guard = torch.zeros_like(physical)
    guard[:, :, 10:15] = 1.0
    rates = torch.tensor([1.0e5, 1.0e6])
    sample_rates = torch.full((2,), config.sample_rate_hz)

    residual = model(physical, guard, normalized_condition(rates, sample_rates))

    assert residual.shape == physical.shape
    assert float(torch.max(torch.abs(residual)).detach()) <= config.interference.max_abs_residual_V
    assert torch.count_nonzero(residual[:, :, 10:15]) == 0


def test_guard_falls_back_to_unmodified_physics() -> None:
    physical = np.linspace(0.0, 1.0, 16, dtype=np.float32)
    residual = np.zeros(16, dtype=np.float32)
    guard = np.zeros(16, dtype=np.bool_)
    guard[5] = True
    residual[5] = 0.01

    result = apply_residual_with_guard(physical, residual, guard, 0.02)

    assert not result.accepted
    assert result.fallback_reason == "event_guard_violation"
    np.testing.assert_array_equal(result.waveform_V, physical)


def test_cpu_rehearsal_writes_explicitly_synthetic_artifacts(tmp_path: Path) -> None:
    artifacts = run_synthetic_residual_rehearsal(compact_config(), tmp_path)
    evaluation = json.loads(artifacts.evaluation_path.read_text(encoding="utf-8"))
    checkpoint = torch.load(artifacts.checkpoint_path, map_location="cpu", weights_only=False)

    assert artifacts.checkpoint_path.exists()
    assert artifacts.example_plot_path.exists()
    assert artifacts.event_guard_violations == 0
    assert artifacts.fallback_count == 0
    assert checkpoint["model_status"] == "synthetic_scaffold"
    assert checkpoint["real_data_calibrated"] is False
    assert checkpoint["scientific_promotion_allowed"] is False
    assert all(tensor.device.type == "cpu" for tensor in checkpoint["model_state"].values())
    assert evaluation["model_status"] == "synthetic_scaffold"
    assert evaluation["real_data_calibrated"] is False
    assert evaluation["scientific_promotion_allowed"] is False
    assert evaluation["truth_event_ledger_modified"] is False
    assert "not trained on calibrated measurements" in artifacts.model_card_path.read_text(
        encoding="utf-8"
    )


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is unavailable")
def test_explicit_cuda_path_executes_one_guarded_forward_pass() -> None:
    config = compact_config()
    device = resolve_device(DeviceMode.CUDA)
    model = EventProtectedResidualTCN(
        config.model,
        config.interference.max_abs_residual_V,
    ).to(device)
    physical = torch.zeros(1, 1, config.patch_samples, device=device)
    guard = torch.zeros_like(physical)
    condition = normalized_condition(
        torch.tensor([1.0e6], device=device),
        torch.tensor([config.sample_rate_hz], device=device),
    )

    residual = model(physical, guard, condition)

    assert residual.device.type == "cuda"
    assert torch.isfinite(residual).all()
