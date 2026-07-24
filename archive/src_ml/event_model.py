"""Likelihood-trained conditional marked point-process model for Phase 5."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import numpy.typing as npt
import torch
from torch import nn
from torch.nn import functional as functional

from he3sim.config import MAX_TRUE_RATE_CPS, MIN_TRUE_RATE_CPS
from he3sim.ml.config import EventModelArchitectureConfig
from he3sim.ml.data import DetectorSpecification, EventBatch
from he3sim.types import TRUE_EVENT_DTYPE

LOG_TWO_PI = math.log(2.0 * math.pi)
UNASSIGNED_INDEX = -1


def _inverse_softplus(value: float) -> float:
    return math.log(math.expm1(value))


def _normal_log_prob(
    value: torch.Tensor, location: torch.Tensor, scale: torch.Tensor
) -> torch.Tensor:
    standardized = (value - location) / scale
    return -0.5 * (standardized.square() + LOG_TWO_PI) - torch.log(scale)


class ConditionalMarkedEventModel(nn.Module):
    """Small conditional density network that never replaces the exact default generator."""

    model_status = "experimental"
    detector_encoding: torch.Tensor
    component_allowed: torch.Tensor
    energy_min_keV: torch.Tensor
    energy_max_keV: torch.Tensor

    def __init__(
        self,
        architecture: EventModelArchitectureConfig,
        detector: DetectorSpecification,
    ) -> None:
        super().__init__()
        self.architecture = architecture
        self.detector = detector
        detector_encoding = torch.tensor(detector.encoding, dtype=torch.float32)
        self.register_buffer("detector_encoding", detector_encoding)
        self.register_buffer(
            "component_allowed",
            torch.tensor([weight > 0.0 for weight in detector.component_weights], dtype=torch.bool),
        )
        self.register_buffer(
            "energy_min_keV",
            torch.tensor(detector.energy_min_keV, dtype=torch.float32),
        )
        self.register_buffer(
            "energy_max_keV",
            torch.tensor(detector.energy_max_keV, dtype=torch.float32),
        )

        input_dim = 3 + len(detector.encoding)
        layers: list[nn.Module] = []
        previous = input_dim
        for _ in range(architecture.hidden_layers):
            layers.extend((nn.Linear(previous, architecture.hidden_dim), nn.SiLU()))
            previous = architecture.hidden_dim
        self.trunk = nn.Sequential(*layers)
        self.count_residual_head = nn.Linear(previous, 1)
        self.interval_head = nn.Linear(previous, 2 * architecture.interval_mixture_components)
        self.component_head = nn.Linear(previous, 4)
        self.energy_head = nn.Linear(previous, 8)
        event_input_dim = previous + 5
        self.amplitude_head = nn.Sequential(
            nn.Linear(event_input_dim, architecture.hidden_dim),
            nn.SiLU(),
            nn.Linear(architecture.hidden_dim, 2),
        )
        self.tau_head = nn.Sequential(
            nn.Linear(previous + 4, architecture.hidden_dim),
            nn.SiLU(),
            nn.Linear(architecture.hidden_dim, 4),
        )
        self._initialize_physical_baseline()

    def _initialize_physical_baseline(self) -> None:
        """Initialize known Poisson terms exactly and learn only density corrections."""
        nn.init.zeros_(self.count_residual_head.weight)
        nn.init.zeros_(self.count_residual_head.bias)
        nn.init.zeros_(self.interval_head.weight)
        nn.init.zeros_(self.interval_head.bias)
        nn.init.zeros_(self.component_head.weight)
        component_bias = torch.log(
            torch.tensor(self.detector.component_weights, dtype=torch.float32).clamp_min(1.0e-12)
        )
        with torch.no_grad():
            self.component_head.bias.copy_(component_bias)
        nn.init.zeros_(self.energy_head.weight)
        energy_bias: list[float] = []
        initial_scale = max(0.7, self.architecture.minimum_scale * 2.0)
        raw_scale = _inverse_softplus(initial_scale - self.architecture.minimum_scale)
        for location in self.detector.energy_initial_logit_mean:
            energy_bias.extend((location, raw_scale))
        with torch.no_grad():
            self.energy_head.bias.copy_(torch.tensor(energy_bias, dtype=torch.float32))
        for module in (*self.amplitude_head, *self.tau_head):
            if isinstance(module, nn.Linear):
                nn.init.zeros_(module.weight)
                nn.init.zeros_(module.bias)
        final_amplitude = self.amplitude_head[-1]
        final_tau = self.tau_head[-1]
        assert isinstance(final_amplitude, nn.Linear)
        assert isinstance(final_tau, nn.Linear)
        density_scale = max(0.10, self.architecture.minimum_scale * 2.0)
        raw_density_scale = _inverse_softplus(density_scale - self.architecture.minimum_scale)
        with torch.no_grad():
            final_amplitude.bias[1] = raw_density_scale
            final_tau.bias[1] = raw_density_scale
            final_tau.bias[3] = raw_density_scale

    @property
    def device(self) -> torch.device:
        """Return the device holding model parameters."""
        return next(self.parameters()).device

    def architecture_dict(self) -> dict[str, Any]:
        """Return a checkpoint-safe architecture description."""
        return self.architecture.model_dump(mode="json")

    def _condition_features(
        self, true_rate_cps: torch.Tensor, duration_s: torch.Tensor
    ) -> torch.Tensor:
        if true_rate_cps.ndim != 1 or duration_s.ndim != 1:
            raise ValueError("rate and duration tensors must be one-dimensional")
        if true_rate_cps.shape != duration_s.shape:
            raise ValueError("rate and duration tensors must have matching shapes")
        if torch.any(true_rate_cps < MIN_TRUE_RATE_CPS) or torch.any(
            true_rate_cps > MAX_TRUE_RATE_CPS
        ):
            raise ValueError("true_rate_cps must remain within [10, 1e7]")
        if torch.any(duration_s <= 0.0):
            raise ValueError("duration_s must be positive")
        log_rate = (torch.log10(true_rate_cps) - 3.5) / 3.5
        log_duration = torch.log10(duration_s) / 8.0
        log_expected = torch.log1p(true_rate_cps * duration_s) / math.log(513.0)
        detector = self.detector_encoding.unsqueeze(0).expand(true_rate_cps.shape[0], -1)
        return torch.cat(
            (log_rate[:, None], log_duration[:, None], log_expected[:, None], detector), dim=1
        )

    def _window_parameters(
        self, true_rate_cps: torch.Tensor, duration_s: torch.Tensor
    ) -> tuple[
        torch.Tensor,
        torch.Tensor,
        torch.Tensor,
        torch.Tensor,
        torch.Tensor,
        torch.Tensor,
    ]:
        hidden = self.trunk(self._condition_features(true_rate_cps, duration_s))
        log_expected = torch.log((true_rate_cps * duration_s).clamp_min(1.0e-8))
        log_count_rate = log_expected + self.count_residual_head(hidden).squeeze(1).clamp(-3, 3)
        interval_raw = self.interval_head(hidden)
        components = self.architecture.interval_mixture_components
        interval_logits = interval_raw[:, :components]
        interval_offsets = interval_raw[:, components:].clamp(-3, 3)
        interval_rates = true_rate_cps[:, None] * torch.exp(interval_offsets)
        component_logits = self.component_head(hidden).masked_fill(
            ~self.component_allowed[None, :], -1.0e9
        )
        energy_raw = self.energy_head(hidden).reshape(-1, 4, 2)
        return hidden, log_count_rate, interval_logits, interval_rates, component_logits, energy_raw

    def _event_distribution_parameters(
        self,
        hidden: torch.Tensor,
        parent: torch.Tensor,
        component_id: torch.Tensor,
        energy_dep_keV: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        one_hot = functional.one_hot(component_id, num_classes=4).to(hidden.dtype)
        energy_scale = self.energy_max_keV[component_id].clamp_min(1.0)
        normalized_energy = (energy_dep_keV / energy_scale).unsqueeze(1)
        event_hidden = hidden[parent]
        amplitude_raw = self.amplitude_head(
            torch.cat((event_hidden, one_hot, normalized_energy), dim=1)
        )
        amplitude_mean = (
            self.detector.gain_V_per_keV * energy_dep_keV + self.detector.offset_V
        ).clamp_min(1.0e-12)
        amplitude_location = torch.log(amplitude_mean) + amplitude_raw[:, 0].clamp(-3, 3)
        amplitude_scale = functional.softplus(amplitude_raw[:, 1]) + self.architecture.minimum_scale
        tau_raw = self.tau_head(torch.cat((event_hidden, one_hot), dim=1))
        tau_r_location = math.log(self.detector.tau_r_s) + tau_raw[:, 0].clamp(-3, 3)
        tau_r_scale = functional.softplus(tau_raw[:, 1]) + self.architecture.minimum_scale
        tau_gap_location = math.log(self.detector.tau_d_s - self.detector.tau_r_s) + tau_raw[
            :, 2
        ].clamp(-3, 3)
        tau_gap_scale = functional.softplus(tau_raw[:, 3]) + self.architecture.minimum_scale
        return (
            amplitude_location,
            amplitude_scale,
            tau_r_location,
            tau_r_scale,
            tau_gap_location,
            tau_gap_scale,
        )

    def negative_log_likelihood(self, batch: EventBatch) -> dict[str, torch.Tensor]:
        """Compute distributional losses for counts, gaps, types, and continuous marks."""
        (
            hidden,
            log_count_rate,
            interval_logits,
            interval_rates,
            component_logits,
            energy_raw,
        ) = self._window_parameters(batch.true_rate_cps, batch.duration_s)
        count_nll = (
            torch.exp(log_count_rate)
            - batch.counts * log_count_rate
            + torch.lgamma(batch.counts + 1.0)
        )
        count_nll = count_nll.mean()
        if batch.event_window_index.numel() == 0:
            zero = count_nll.new_zeros(())
            return {
                "total": count_nll,
                "count": count_nll,
                "interval": zero,
                "event_type": zero,
                "energy": zero,
                "amplitude": zero,
                "tau": zero,
            }
        parent = batch.event_window_index
        log_weights = functional.log_softmax(interval_logits[parent], dim=1)
        rates = interval_rates[parent]
        interval_log_prob = torch.logsumexp(
            log_weights + torch.log(rates) - rates * batch.intervals_s[:, None], dim=1
        )
        interval_nll = -interval_log_prob.mean()
        event_type_nll = functional.cross_entropy(component_logits[parent], batch.component_id)

        selected_energy = energy_raw[parent, batch.component_id]
        energy_location = selected_energy[:, 0]
        energy_scale = functional.softplus(selected_energy[:, 1]) + self.architecture.minimum_scale
        minimum = self.energy_min_keV[batch.component_id]
        width = self.energy_max_keV[batch.component_id] - minimum
        unit_energy = ((batch.energy_dep_keV - minimum) / width).clamp(1.0e-6, 1.0 - 1.0e-6)
        logit_energy = torch.logit(unit_energy)
        energy_log_prob = (
            _normal_log_prob(logit_energy, energy_location, energy_scale)
            - torch.log(width)
            - torch.log(unit_energy)
            - torch.log1p(-unit_energy)
        )
        energy_nll = -energy_log_prob.mean()

        (
            amplitude_location,
            amplitude_scale,
            tau_r_location,
            tau_r_scale,
            tau_gap_location,
            tau_gap_scale,
        ) = self._event_distribution_parameters(
            hidden, parent, batch.component_id, batch.energy_dep_keV
        )
        log_amplitude = torch.log(batch.amplitude_peak_V)
        amplitude_nll = -(
            _normal_log_prob(log_amplitude, amplitude_location, amplitude_scale) - log_amplitude
        ).mean()
        log_tau_r = torch.log(batch.tau_r_s)
        tau_gap = batch.tau_d_s - batch.tau_r_s
        log_tau_gap = torch.log(tau_gap)
        tau_nll = -0.5 * (
            (_normal_log_prob(log_tau_r, tau_r_location, tau_r_scale) - log_tau_r).mean()
            + (_normal_log_prob(log_tau_gap, tau_gap_location, tau_gap_scale) - log_tau_gap).mean()
        )
        total = count_nll + interval_nll + event_type_nll + energy_nll + amplitude_nll + tau_nll
        return {
            "total": total,
            "count": count_nll,
            "interval": interval_nll,
            "event_type": event_type_nll,
            "energy": energy_nll,
            "amplitude": amplitude_nll,
            "tau": tau_nll,
        }

    @torch.no_grad()
    def generate(
        self,
        true_rate_cps: float,
        window_duration_s: float,
        *,
        seed: int,
        max_events: int,
    ) -> npt.NDArray[np.void]:
        """Sample one ordered legal event table from learned conditional densities."""
        if not MIN_TRUE_RATE_CPS <= true_rate_cps <= MAX_TRUE_RATE_CPS:
            raise ValueError("true_rate_cps must remain within [10, 1e7]")
        if not np.isfinite(window_duration_s) or window_duration_s <= 0.0:
            raise ValueError("window_duration_s must be finite and positive")
        if seed < 0 or max_events <= 0:
            raise ValueError("seed must be non-negative and max_events must be positive")
        self.eval()
        device = self.device
        generator = torch.Generator(device=device)
        generator.manual_seed(seed)
        rate = torch.tensor([true_rate_cps], dtype=torch.float32, device=device)
        duration = torch.tensor([window_duration_s], dtype=torch.float32, device=device)
        (
            hidden,
            log_count_rate,
            interval_logits,
            interval_rates,
            component_logits,
            energy_raw,
        ) = self._window_parameters(rate, duration)
        count = int(torch.poisson(torch.exp(log_count_rate), generator=generator).item())
        if count > max_events:
            raise ValueError(
                f"model realized {count} events, exceeding the explicit max_events={max_events}"
            )
        events = np.empty(count, dtype=TRUE_EVENT_DTYPE)
        if count == 0:
            return events

        gap_weights = functional.softmax(interval_logits[0], dim=0)
        gap_components = torch.multinomial(
            gap_weights, count + 1, replacement=True, generator=generator
        )
        gap_rates = interval_rates[0, gap_components].to(torch.float64)
        uniforms = torch.rand(
            count + 1, dtype=torch.float64, device=device, generator=generator
        ).clamp_min(1.0e-12)
        positive_gaps = -torch.log(uniforms) / gap_rates
        times = (
            torch.cumsum(positive_gaps[:-1], dim=0) / torch.sum(positive_gaps) * window_duration_s
        )

        type_probabilities = functional.softmax(component_logits[0], dim=0)
        component_id = torch.multinomial(
            type_probabilities, count, replacement=True, generator=generator
        )
        selected_energy = energy_raw[0, component_id]
        energy_location = selected_energy[:, 0]
        energy_scale = functional.softplus(selected_energy[:, 1]) + self.architecture.minimum_scale
        energy_latent = energy_location + energy_scale * torch.randn(
            count, dtype=torch.float32, device=device, generator=generator
        )
        minimum = self.energy_min_keV[component_id]
        maximum = self.energy_max_keV[component_id]
        energy = minimum + (maximum - minimum) * torch.sigmoid(energy_latent)

        parent = torch.zeros(count, dtype=torch.long, device=device)
        (
            amplitude_location,
            amplitude_scale,
            tau_r_location,
            tau_r_scale,
            tau_gap_location,
            tau_gap_scale,
        ) = self._event_distribution_parameters(hidden, parent, component_id, energy)
        amplitude = torch.exp(
            amplitude_location
            + amplitude_scale
            * torch.randn(count, dtype=torch.float32, device=device, generator=generator)
        )
        tau_r = torch.exp(
            tau_r_location
            + tau_r_scale
            * torch.randn(count, dtype=torch.float32, device=device, generator=generator)
        )
        tau_gap = torch.exp(
            tau_gap_location
            + tau_gap_scale
            * torch.randn(count, dtype=torch.float32, device=device, generator=generator)
        )
        times_np = times.cpu().numpy()
        if np.any(np.diff(times_np) <= 0.0) or times_np[-1] >= window_duration_s:
            raise RuntimeError("model failed to produce strictly ordered in-window events")
        energy_np = energy.cpu().numpy().astype(np.float64)
        amplitude_np = amplitude.cpu().numpy().astype(np.float64)
        tau_r_np = tau_r.cpu().numpy().astype(np.float64)
        tau_d_np = tau_r_np + tau_gap.cpu().numpy().astype(np.float64)
        component_np = component_id.cpu().numpy().astype(np.int16)
        if (
            np.any(~np.isfinite(energy_np))
            or np.any(energy_np < 0.0)
            or np.any(~np.isfinite(amplitude_np))
            or np.any(amplitude_np <= 0.0)
            or np.any(~np.isfinite(tau_r_np))
            or np.any(tau_r_np <= 0.0)
            or np.any(tau_d_np <= tau_r_np)
        ):
            raise RuntimeError("model produced an illegal continuous mark")

        events["event_id"] = np.arange(count, dtype=np.int64)
        events["t_s"] = times_np
        events["energy_dep_keV"] = energy_np
        events["spectrum_component_id"] = component_np
        events["amplitude_peak_V"] = amplitude_np
        events["tau_r_s"] = tau_r_np
        events["tau_d_s"] = tau_d_np
        events["polarity"] = self.detector.polarity
        events["block_id"] = UNASSIGNED_INDEX
        events["sample_index"] = UNASSIGNED_INDEX
        events["pileup_group_id"] = UNASSIGNED_INDEX
        events["parameter_status"] = self.detector.parameter_status.value.encode("ascii")
        return events
