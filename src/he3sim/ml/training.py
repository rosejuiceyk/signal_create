"""Deterministic likelihood training and checkpoints for Phase 5."""

from __future__ import annotations

import json
import platform
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

from he3sim.config import config_hash, load_config
from he3sim.ml.config import (
    STANDARD_RATES_CPS,
    EventModelArchitectureConfig,
    EventModelTrainingConfig,
    MLDevice,
    ml_config_hash,
)
from he3sim.ml.data import (
    DetectorSpecification,
    EventWindow,
    ExactPhysicsWindowSampler,
    collate_event_windows,
    detector_specification,
    generate_fixed_rate_windows,
    generate_log_uniform_windows,
)
from he3sim.ml.event_model import ConditionalMarkedEventModel


def resolve_torch_device(mode: MLDevice) -> torch.device:
    """Resolve an explicit device, rejecting unavailable CUDA without silent fallback."""
    if mode is MLDevice.CUDA:
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but this PyTorch build cannot access CUDA")
        return torch.device("cuda")
    if mode is MLDevice.AUTO and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def synchronize_device(device: torch.device) -> None:
    """Synchronize CUDA timing while remaining a no-op on CPU."""
    if device.type == "cuda":
        torch.cuda.synchronize(device)


@dataclass(frozen=True, slots=True)
class TrainingArtifacts:
    """Paths and observed training facts returned to the CLI."""

    checkpoint_path: Path
    model_card_path: Path
    summary_path: Path
    device: str
    epochs_completed: int
    best_validation_nll: float


def _batch_iterator(
    windows: Sequence[EventWindow],
    batch_size: int,
    rng: np.random.Generator,
    *,
    shuffle: bool,
) -> Iterator[list[EventWindow]]:
    indices = np.arange(len(windows), dtype=np.int64)
    if shuffle:
        rng.shuffle(indices)
    for start in range(0, indices.size, batch_size):
        yield [windows[int(index)] for index in indices[start : start + batch_size]]


def _mean_epoch_loss(
    model: ConditionalMarkedEventModel,
    windows: Sequence[EventWindow],
    batch_size: int,
    device: torch.device,
) -> float:
    model.eval()
    losses: list[float] = []
    rng = np.random.default_rng(0)
    with torch.no_grad():
        for window_batch in _batch_iterator(windows, batch_size, rng, shuffle=False):
            loss = model.negative_log_likelihood(collate_event_windows(window_batch).to(device))[
                "total"
            ]
            losses.append(float(loss.detach().cpu()))
    return float(np.mean(losses))


def _checkpoint_payload(
    model: ConditionalMarkedEventModel,
    optimizer: torch.optim.Optimizer,
    config: EventModelTrainingConfig,
    *,
    epoch: int,
    history: list[dict[str, float]],
    base_config_hash: str,
) -> dict[str, Any]:
    return {
        "format_version": 1,
        "model_status": "experimental",
        "epoch": epoch,
        "model_state": model.state_dict(),
        "optimizer_state": optimizer.state_dict(),
        "architecture": model.architecture_dict(),
        "detector_specification": model.detector.to_dict(),
        "training_config": config.model_dump(mode="json"),
        "training_config_hash": ml_config_hash(config),
        "base_config_hash": base_config_hash,
        "history": history,
        "torch_version": str(torch.__version__),
    }


def _save_checkpoint(payload: dict[str, Any], output_directory: Path, epoch: int) -> Path:
    output_directory.mkdir(parents=True, exist_ok=True)
    epoch_path = output_directory / f"checkpoint_epoch_{epoch:04d}.pt"
    latest_path = output_directory / "checkpoint_latest.pt"
    torch.save(payload, epoch_path)
    torch.save(payload, latest_path)
    return latest_path


def load_event_model_checkpoint(
    path: str | Path,
    device: torch.device,
) -> tuple[ConditionalMarkedEventModel, dict[str, Any]]:
    """Load a local Phase 5 checkpoint with architecture and detector constraints."""
    checkpoint_path = Path(path)
    try:
        payload: dict[str, Any] = torch.load(
            checkpoint_path, map_location=device, weights_only=True
        )
    except (OSError, RuntimeError, TypeError) as exc:
        raise ValueError(f"failed to load Phase 5 checkpoint: {checkpoint_path}") from exc
    if payload.get("format_version") != 1 or payload.get("model_status") != "experimental":
        raise ValueError("unsupported or non-experimental event-model checkpoint")
    architecture = EventModelArchitectureConfig.model_validate(payload["architecture"])
    detector = DetectorSpecification.from_dict(payload["detector_specification"])
    model = ConditionalMarkedEventModel(architecture, detector).to(device)
    model.load_state_dict(payload["model_state"])
    model.eval()
    return model, payload


def _write_model_card(
    path: Path,
    *,
    model: ConditionalMarkedEventModel,
    config: EventModelTrainingConfig,
    base_config_hash: str,
    device: torch.device,
    history: list[dict[str, float]],
    elapsed_s: float,
    peak_cuda_bytes: int,
) -> None:
    final = history[-1]
    text = f"""# Phase 5 conditional marked-event model card

- Status: `experimental`
- Default generator: exact Poisson + parametric spectrum (unchanged)
- Training target: independently generated `synthetic_demo` Phase 1 windows
- Base config hash: `{base_config_hash}`
- Training config hash: `{ml_config_hash(config)}`
- Device: `{device}`
- PyTorch: `{torch.__version__}`
- Parameter count: `{sum(parameter.numel() for parameter in model.parameters())}`
- Epochs: `{len(history)}`
- Final training NLL: `{final["training_nll"]:.8g}`
- Final validation NLL: `{final["validation_nll"]:.8g}`
- Training wall time: `{elapsed_s:.6f} s`
- Peak CUDA allocation: `{peak_cuda_bytes} bytes`

## Intended use

Research comparison of a likelihood-trained conditional marked point process against the known exact
synthetic generator. The model accepts true rate, window duration, a detector/config encoding, and
seeded stochastic latent draws. It outputs a variable-length ordered event table.

## Distribution heads and constraints

- Poisson event-count likelihood with a learned bounded residual around `rate * duration`;
- positive mixture-of-exponentials interval likelihood;
- categorical event-type likelihood with unsupported configured components masked out;
- event-type-bounded logistic-normal energy likelihood;
- positive log-normal amplitude, rise-time and decay-gap likelihoods;
- `tau_d > tau_r > 0`, positive amplitude, non-negative energy, valid type and strict time order.

## Limitations

No Phase 4 real calibration data were used. The detector encoding represents one synthetic demo
config, not a measured instrument population. Passing statistical comparison does not authorize
replacing the exact physical baseline. A separate comparison report is required, and the model
remains experimental.
"""
    path.write_text(text, encoding="utf-8")


def train_event_model(config: EventModelTrainingConfig) -> TrainingArtifacts:
    """Train, validate, checkpoint, and document one experimental event model."""
    device = resolve_torch_device(config.device)
    torch.manual_seed(config.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(config.seed)
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    base_config = load_config(config.base_config_path)
    base_hash = config_hash(base_config)
    detector = detector_specification(base_config)
    sampler = ExactPhysicsWindowSampler(base_config)
    training_windows = generate_log_uniform_windows(
        sampler,
        count=config.train_windows,
        rate_min_cps=config.rate_min_cps,
        rate_max_cps=config.rate_max_cps,
        expected_events_min=config.expected_events_min,
        expected_events_max=config.expected_events_max,
        max_events=config.max_events_per_window,
        seed=config.seed,
    )
    validation_windows = generate_fixed_rate_windows(
        sampler,
        STANDARD_RATES_CPS,
        total_windows=config.validation_windows,
        expected_events=(config.expected_events_min * config.expected_events_max) ** 0.5,
        max_events=config.max_events_per_window,
        seed=config.seed + 1,
    )
    model = ConditionalMarkedEventModel(config.architecture, detector).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    start_epoch = 0
    history: list[dict[str, float]] = []
    if config.resume_from is not None:
        resumed_model, payload = load_event_model_checkpoint(config.resume_from, device)
        if payload["base_config_hash"] != base_hash:
            raise ValueError("resume checkpoint base config hash does not match")
        if resumed_model.architecture != model.architecture:
            raise ValueError("resume checkpoint architecture does not match")
        model.load_state_dict(resumed_model.state_dict())
        optimizer.load_state_dict(payload["optimizer_state"])
        start_epoch = int(payload["epoch"])
        history = [dict(item) for item in payload["history"]]

    output_directory = config.output_directory
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "training_config.json").write_text(
        json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    rng = np.random.default_rng(config.seed + 2)
    started = time.perf_counter()
    latest_path = output_directory / "checkpoint_latest.pt"
    for epoch in range(start_epoch + 1, config.epochs + 1):
        model.train()
        train_losses: list[float] = []
        for window_batch in _batch_iterator(training_windows, config.batch_size, rng, shuffle=True):
            optimizer.zero_grad(set_to_none=True)
            losses = model.negative_log_likelihood(collate_event_windows(window_batch).to(device))
            loss = losses["total"]
            if not torch.isfinite(loss):
                raise RuntimeError("event-model training produced a non-finite likelihood")
            loss.backward()  # type: ignore[no-untyped-call]
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=10.0)
            optimizer.step()
            train_losses.append(float(loss.detach().cpu()))
        validation_nll = _mean_epoch_loss(model, validation_windows, config.batch_size, device)
        history.append(
            {
                "epoch": float(epoch),
                "training_nll": float(np.mean(train_losses)),
                "validation_nll": validation_nll,
            }
        )
        if epoch % config.checkpoint_every == 0 or epoch == config.epochs:
            latest_path = _save_checkpoint(
                _checkpoint_payload(
                    model,
                    optimizer,
                    config,
                    epoch=epoch,
                    history=history,
                    base_config_hash=base_hash,
                ),
                output_directory,
                epoch,
            )
    synchronize_device(device)
    elapsed_s = time.perf_counter() - started
    peak_cuda_bytes = int(torch.cuda.max_memory_allocated(device)) if device.type == "cuda" else 0
    best_validation = min(item["validation_nll"] for item in history)
    summary = {
        "model_status": "experimental",
        "default_generator": "exact_poisson_parametric_spectrum",
        "device": str(device),
        "cuda_available": torch.cuda.is_available(),
        "cuda_device_name": (torch.cuda.get_device_name(device) if device.type == "cuda" else None),
        "torch_version": str(torch.__version__),
        "python_version": platform.python_version(),
        "epochs_completed": config.epochs,
        "best_validation_nll": best_validation,
        "training_wall_time_s": elapsed_s,
        "peak_cuda_allocated_bytes": peak_cuda_bytes,
        "checkpoint": latest_path.name,
        "base_config_hash": base_hash,
        "training_config_hash": ml_config_hash(config),
        "history": history,
    }
    summary_path = output_directory / "training_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    model_card_path = output_directory / "MODEL_CARD.md"
    _write_model_card(
        model_card_path,
        model=model,
        config=config,
        base_config_hash=base_hash,
        device=device,
        history=history,
        elapsed_s=elapsed_s,
        peak_cuda_bytes=peak_cuda_bytes,
    )
    return TrainingArtifacts(
        checkpoint_path=latest_path,
        model_card_path=model_card_path,
        summary_path=summary_path,
        device=str(device),
        epochs_completed=config.epochs,
        best_validation_nll=best_validation,
    )
