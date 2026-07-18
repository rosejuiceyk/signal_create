"""Train and evaluate the explicitly synthetic Phase 6S residual scaffold."""

from __future__ import annotations

import csv
import json
import math
import time
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import torch
from torch import Tensor, nn
from torch.nn import functional as F
from torch.utils.data import DataLoader, TensorDataset

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from he3sim.ml.residual_config import (
    DeviceMode,
    SyntheticResidualRehearsalConfig,
    synthetic_residual_config_hash,
    synthetic_residual_config_payload,
)
from he3sim.ml.residual_data import SyntheticResidualPatch, build_synthetic_residual_dataset
from he3sim.ml.residual_model import EventProtectedResidualTCN, normalized_condition
from he3sim.ml.residual_safety import apply_residual_with_guard


@dataclass(frozen=True, slots=True)
class RehearsalArtifacts:
    """Paths and headline evidence from one complete synthetic rehearsal."""

    output_directory: Path
    checkpoint_path: Path
    model_card_path: Path
    training_summary_path: Path
    evaluation_path: Path
    comparison_path: Path
    example_plot_path: Path
    device: str
    synthetic_recovery_improved: bool
    event_guard_violations: int
    fallback_count: int


def _package_version() -> str:
    try:
        return version("he3-pulse-sim")
    except PackageNotFoundError:
        return "uninstalled"


def resolve_device(mode: DeviceMode) -> torch.device:
    """Resolve an explicit device and never silently ignore a CUDA request."""
    if mode is DeviceMode.CPU:
        return torch.device("cpu")
    if mode is DeviceMode.CUDA:
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA was explicitly requested but is unavailable")
        return torch.device("cuda")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _set_determinism(seed: int) -> None:
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True


def _tensor_dataset(patches: list[SyntheticResidualPatch]) -> TensorDataset:
    physical = torch.from_numpy(np.stack([patch.physical_waveform_V for patch in patches]))
    target = torch.from_numpy(np.stack([patch.artificial_residual_V for patch in patches]))
    guard = torch.from_numpy(
        np.stack([patch.event_guard_mask for patch in patches]).astype(np.float32)
    )
    rates = torch.tensor([patch.true_rate_cps for patch in patches], dtype=torch.float32)
    sample_rates = torch.tensor([patch.sample_rate_hz for patch in patches], dtype=torch.float32)
    return TensorDataset(
        physical.unsqueeze(1),
        target.unsqueeze(1),
        guard.unsqueeze(1),
        rates,
        sample_rates,
    )


def _spectral_loss(predicted: Tensor, target: Tensor) -> Tensor:
    losses: list[Tensor] = []
    for stride in (1, 4):
        pred_spectrum = torch.fft.rfft(predicted[..., ::stride], dim=-1)
        target_spectrum = torch.fft.rfft(target[..., ::stride], dim=-1)
        losses.append(
            F.l1_loss(
                torch.log1p(torch.abs(pred_spectrum)), torch.log1p(torch.abs(target_spectrum))
            )
        )
    return torch.stack(losses).mean()


def _loss_terms(
    predicted_V: Tensor,
    target_V: Tensor,
    guard_mask: Tensor,
    config: SyntheticResidualRehearsalConfig,
) -> dict[str, Tensor]:
    scale = config.interference.max_abs_residual_V
    predicted = predicted_V / scale
    target = target_V / scale
    non_event = 1.0 - guard_mask
    non_event_count = torch.clamp(non_event.sum(), min=1.0)
    terms = {
        "huber": F.smooth_l1_loss(predicted, target, beta=0.05),
        "spectral": _spectral_loss(predicted, target),
        "baseline": torch.sum(torch.abs(predicted - target) * non_event) / non_event_count,
        "event_guard": torch.mean(torch.abs(predicted * guard_mask)),
        "residual_energy": torch.mean(predicted * predicted),
    }
    weights = config.training
    terms["total"] = (
        weights.huber_weight * terms["huber"]
        + weights.spectral_weight * terms["spectral"]
        + weights.baseline_weight * terms["baseline"]
        + weights.event_guard_weight * terms["event_guard"]
        + weights.residual_energy_weight * terms["residual_energy"]
    )
    return terms


def _mean_loader_loss(
    model: EventProtectedResidualTCN,
    loader: DataLoader[tuple[Tensor, ...]],
    device: torch.device,
    config: SyntheticResidualRehearsalConfig,
) -> float:
    model.eval()
    total = 0.0
    batches = 0
    with torch.no_grad():
        for physical, target, guard, rates, sample_rates in loader:
            physical = physical.to(device)
            target = target.to(device)
            guard = guard.to(device)
            condition = normalized_condition(rates.to(device), sample_rates.to(device))
            predicted = model(physical, guard, condition)
            total += float(_loss_terms(predicted, target, guard, config)["total"].item())
            batches += 1
    if batches == 0:
        raise RuntimeError("validation loader contained no batches")
    return total / batches


def _train(
    config: SyntheticResidualRehearsalConfig,
    dataset: dict[str, list[SyntheticResidualPatch]],
    device: torch.device,
) -> tuple[EventProtectedResidualTCN, list[dict[str, float]], float, int]:
    _set_determinism(config.training.seed)
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    model = EventProtectedResidualTCN(
        config.model,
        config.interference.max_abs_residual_V,
    ).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.training.learning_rate)
    generator = torch.Generator().manual_seed(config.training.seed)
    train_loader = DataLoader(
        _tensor_dataset(dataset["train"]),
        batch_size=config.training.batch_size,
        shuffle=True,
        generator=generator,
    )
    validation_loader = DataLoader(
        _tensor_dataset(dataset["validation"]),
        batch_size=config.training.batch_size,
        shuffle=False,
    )
    history: list[dict[str, float]] = []
    best_state: dict[str, Tensor] | None = None
    best_validation = math.inf
    started = time.perf_counter()
    for epoch in range(1, config.training.epochs + 1):
        model.train()
        running = 0.0
        batches = 0
        for physical, target, guard, rates, sample_rates in train_loader:
            physical = physical.to(device)
            target = target.to(device)
            guard = guard.to(device)
            condition = normalized_condition(rates.to(device), sample_rates.to(device))
            optimizer.zero_grad(set_to_none=True)
            predicted = model(physical, guard, condition)
            loss = _loss_terms(predicted, target, guard, config)["total"]
            torch.autograd.backward(loss)
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
            running += float(loss.item())
            batches += 1
        validation = _mean_loader_loss(model, validation_loader, device, config)
        train_mean = running / max(1, batches)
        history.append(
            {"epoch": float(epoch), "train_loss": train_mean, "validation_loss": validation}
        )
        if validation < best_validation:
            best_validation = validation
            best_state = {
                name: value.detach().cpu().clone() for name, value in model.state_dict().items()
            }
    if best_state is None:
        raise RuntimeError("training did not produce a checkpoint state")
    model.load_state_dict(best_state)
    model.to(device)
    elapsed = time.perf_counter() - started
    peak_cuda_bytes = int(torch.cuda.max_memory_allocated(device)) if device.type == "cuda" else 0
    return model, history, elapsed, peak_cuda_bytes


def _predict_patch(
    model: EventProtectedResidualTCN,
    patch: SyntheticResidualPatch,
    device: torch.device,
) -> np.ndarray[Any, np.dtype[np.float32]]:
    physical = torch.from_numpy(patch.physical_waveform_V).view(1, 1, -1).to(device)
    guard = torch.from_numpy(patch.event_guard_mask.astype(np.float32)).view(1, 1, -1).to(device)
    rates = torch.tensor([patch.true_rate_cps], dtype=torch.float32, device=device)
    sample_rates = torch.tensor([patch.sample_rate_hz], dtype=torch.float32, device=device)
    model.eval()
    with torch.no_grad():
        predicted = model(physical, guard, normalized_condition(rates, sample_rates))
    return np.asarray(predicted.squeeze().cpu().numpy(), dtype=np.float32)


def _rmse(left: np.ndarray[Any, Any], right: np.ndarray[Any, Any]) -> float:
    return float(np.sqrt(np.mean((left.astype(np.float64) - right.astype(np.float64)) ** 2)))


def _spectral_error(left: np.ndarray[Any, Any], right: np.ndarray[Any, Any]) -> float:
    left_spectrum = np.log1p(np.abs(np.fft.rfft(left.astype(np.float64))))
    right_spectrum = np.log1p(np.abs(np.fft.rfft(right.astype(np.float64))))
    return float(np.mean(np.abs(left_spectrum - right_spectrum)))


def _evaluate(
    model: EventProtectedResidualTCN,
    patches: list[SyntheticResidualPatch],
    device: torch.device,
    config: SyntheticResidualRehearsalConfig,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[np.ndarray[Any, np.dtype[np.float32]]]]:
    rows: list[dict[str, Any]] = []
    predictions: list[np.ndarray[Any, np.dtype[np.float32]]] = []
    for patch in patches:
        predicted = _predict_patch(model, patch, device)
        guarded = apply_residual_with_guard(
            patch.physical_waveform_V,
            predicted,
            patch.event_guard_mask,
            config.interference.max_abs_residual_V,
        )
        corrected = guarded.waveform_V
        physical_rmse = _rmse(patch.physical_waveform_V, patch.target_waveform_V)
        corrected_rmse = _rmse(corrected, patch.target_waveform_V)
        rows.append(
            {
                "run_id": patch.run_id,
                "true_rate_cps": patch.true_rate_cps,
                "seed": patch.seed,
                "true_event_count": patch.true_event_count,
                "physical_to_target_rmse_V": physical_rmse,
                "corrected_to_target_rmse_V": corrected_rmse,
                "relative_rmse_improvement": (
                    1.0 - corrected_rmse / physical_rmse if physical_rmse > 0.0 else 0.0
                ),
                "residual_rmse_V": _rmse(predicted, patch.artificial_residual_V),
                "physical_spectral_error": _spectral_error(
                    patch.physical_waveform_V, patch.target_waveform_V
                ),
                "corrected_spectral_error": _spectral_error(corrected, patch.target_waveform_V),
                "event_guard_max_abs_V": float(
                    np.max(np.abs(predicted[patch.event_guard_mask]), initial=0.0)
                ),
                "accepted": guarded.accepted,
                "fallback_reason": guarded.fallback_reason,
            }
        )
        predictions.append(predicted)
    physical_mean = float(np.mean([row["physical_to_target_rmse_V"] for row in rows]))
    corrected_mean = float(np.mean([row["corrected_to_target_rmse_V"] for row in rows]))
    summary: dict[str, Any] = {
        "model_status": "synthetic_scaffold",
        "real_data_calibrated": False,
        "scientific_promotion_allowed": False,
        "test_run_count": len(rows),
        "test_truth_event_count": int(sum(int(row["true_event_count"]) for row in rows)),
        "physical_to_target_rmse_V": physical_mean,
        "corrected_to_target_rmse_V": corrected_mean,
        "relative_rmse_improvement": (
            1.0 - corrected_mean / physical_mean if physical_mean > 0.0 else 0.0
        ),
        "physical_spectral_error": float(np.mean([row["physical_spectral_error"] for row in rows])),
        "corrected_spectral_error": float(
            np.mean([row["corrected_spectral_error"] for row in rows])
        ),
        "event_guard_violations": int(
            sum(float(row["event_guard_max_abs_V"]) > 1.0e-8 for row in rows)
        ),
        "fallback_count": int(sum(not bool(row["accepted"]) for row in rows)),
        "truth_event_ledger_modified": False,
    }
    summary["synthetic_recovery_improved"] = bool(
        corrected_mean < physical_mean and summary["event_guard_violations"] == 0
    )
    return summary, rows, predictions


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("cannot write an empty metrics table")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _plot_example(
    path: Path,
    patch: SyntheticResidualPatch,
    predicted_residual_V: np.ndarray[Any, np.dtype[np.float32]],
) -> None:
    time_us = np.arange(patch.physical_waveform_V.size) / patch.sample_rate_hz * 1.0e6
    corrected = patch.physical_waveform_V + predicted_residual_V
    figure, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True, constrained_layout=True)
    axes[0].plot(time_us, patch.physical_waveform_V, label="physical B0", linewidth=1.0)
    axes[0].plot(time_us, patch.target_waveform_V, label="artificial target", linewidth=0.9)
    axes[0].set_ylabel("Voltage (V)")
    axes[0].legend()
    axes[1].plot(time_us, patch.target_waveform_V, label="artificial target", linewidth=1.0)
    axes[1].plot(time_us, corrected, label="physics + predicted residual", linewidth=0.9)
    axes[1].set_ylabel("Voltage (V)")
    axes[1].legend()
    axes[2].plot(
        time_us,
        patch.artificial_residual_V,
        label="known artificial residual",
        linewidth=1.0,
    )
    axes[2].plot(time_us, predicted_residual_V, label="predicted residual", linewidth=0.9)
    axes[2].fill_between(
        time_us,
        -0.001,
        0.001,
        where=patch.event_guard_mask,
        alpha=0.2,
        label="event guard",
    )
    axes[2].set_ylabel("Residual (V)")
    axes[2].set_xlabel("Time (us)")
    axes[2].legend()
    figure.suptitle(
        "Phase 6S synthetic rehearsal - not calibrated real-detector performance\n"
        f"rate={patch.true_rate_cps:.6g} cps | events={patch.true_event_count} | seed={patch.seed}"
    )
    figure.savefig(path, dpi=160)
    plt.close(figure)


def run_synthetic_residual_rehearsal(
    config: SyntheticResidualRehearsalConfig,
    output_directory: str | Path,
) -> RehearsalArtifacts:
    """Run bounded synthetic training/evaluation and write an auditable evidence package."""
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    device = resolve_device(config.training.device)
    dataset = build_synthetic_residual_dataset(config)
    model, history, elapsed_s, peak_cuda_bytes = _train(config, dataset, device)
    evaluation, rate_rows, predictions = _evaluate(model, dataset["test"], device, config)
    config_hash = synthetic_residual_config_hash(config)
    checkpoint_path = output / "residual_scaffold.pt"
    torch.save(
        {
            "model_state": {
                name: value.detach().cpu() for name, value in model.state_dict().items()
            },
            "config": synthetic_residual_config_payload(config),
            "config_hash": config_hash,
            "model_status": "synthetic_scaffold",
            "real_data_calibrated": False,
            "scientific_promotion_allowed": False,
        },
        checkpoint_path,
    )
    manifest_rows = [
        {
            "run_id": patch.run_id,
            "split": patch.split,
            "true_rate_cps": patch.true_rate_cps,
            "sample_rate_hz": patch.sample_rate_hz,
            "seed": patch.seed,
            "true_event_count": patch.true_event_count,
            "patch_samples": patch.physical_waveform_V.size,
            "parameter_status": "synthetic_demo",
        }
        for patches in dataset.values()
        for patch in patches
    ]
    _write_csv(output / "synthetic_run_manifest.csv", manifest_rows)
    _write_csv(output / "test_run_metrics.csv", rate_rows)
    training_summary = {
        "model_status": "synthetic_scaffold",
        "real_data_calibrated": False,
        "scientific_promotion_allowed": False,
        "device": str(device),
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "elapsed_s": elapsed_s,
        "peak_cuda_allocated_bytes": peak_cuda_bytes,
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "config_hash": config_hash,
        "physical_config_path": str(config.physical_config_path),
        "code_version": _package_version(),
        "history": history,
        "split_run_counts": {name: len(patches) for name, patches in dataset.items()},
    }
    training_summary_path = output / "training_summary.json"
    training_summary_path.write_text(
        json.dumps(training_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    evaluation_path = output / "evaluation.json"
    evaluation_path.write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    comparison_path = output / "comparison.md"
    comparison_path.write_text(
        "# Phase 6S synthetic residual comparison\n\n"
        "> This is an engineering rehearsal with artificial interference. It is not measured "
        "He-3 detector validation and cannot promote the model into the formal Phase 6 chain.\n\n"
        f"- Device: `{device}`\n"
        f"- Test runs: {evaluation['test_run_count']}\n"
        f"- Test truth events retained: {evaluation['test_truth_event_count']}\n"
        f"- Physical-to-artificial-target RMSE: {evaluation['physical_to_target_rmse_V']:.8g} V\n"
        f"- Corrected-to-artificial-target RMSE: "
        f"{evaluation['corrected_to_target_rmse_V']:.8g} V\n"
        f"- Relative synthetic RMSE improvement: "
        f"{evaluation['relative_rmse_improvement']:.4%}\n"
        f"- Event-guard violations: {evaluation['event_guard_violations']}\n"
        f"- Safety fallbacks: {evaluation['fallback_count']}\n"
        "- Synthetic recovery improved: "
        f"`{str(evaluation['synthetic_recovery_improved']).lower()}`\n",
        encoding="utf-8",
    )
    model_card_path = output / "model_card.md"
    model_card_path.write_text(
        "# Event-protected residual TCN - synthetic scaffold\n\n"
        "## Intended use\n\n"
        "Engineering rehearsal for a future calibrated residual model. The exact Poisson "
        "physical simulator remains the sole truth-event generator and default waveform path.\n\n"
        "## Prohibited claims\n\n"
        "This checkpoint is not trained on calibrated measurements, does not establish real "
        "detector fidelity, and must not be used as Phase 6 scientific evidence or hardware "
        "readiness evidence.\n\n"
        "## Constraints\n\n"
        "The network receives no writable truth-event ledger. Its residual is bounded, forced "
        "to zero on event guards, and rejected in favor of the pure physical waveform if "
        "shape, finiteness, amplitude, or event-guard checks fail.\n\n"
        f"- Model status: `synthetic_scaffold`\n"
        f"- Real data calibrated: `false`\n"
        f"- Scientific promotion allowed: `false`\n"
        f"- Config hash: `{config_hash}`\n",
        encoding="utf-8",
    )
    example_plot_path = output / "synthetic_residual_example.png"
    _plot_example(example_plot_path, dataset["test"][0], predictions[0])
    return RehearsalArtifacts(
        output_directory=output,
        checkpoint_path=checkpoint_path,
        model_card_path=model_card_path,
        training_summary_path=training_summary_path,
        evaluation_path=evaluation_path,
        comparison_path=comparison_path,
        example_plot_path=example_plot_path,
        device=str(device),
        synthetic_recovery_improved=bool(evaluation["synthetic_recovery_improved"]),
        event_guard_violations=int(evaluation["event_guard_violations"]),
        fallback_count=int(evaluation["fallback_count"]),
    )
