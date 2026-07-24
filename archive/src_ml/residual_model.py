"""Small event-protected FiLM TCN for the Phase 6S rehearsal."""

from __future__ import annotations

import torch
from torch import Tensor, nn

from he3sim.ml.residual_config import ResidualTCNConfig


class FiLMResidualBlock(nn.Module):
    """One same-length dilated residual block with conditional affine modulation."""

    def __init__(self, channels: int, kernel_size: int, dilation: int) -> None:
        super().__init__()
        padding = dilation * (kernel_size - 1) // 2
        self.conv1 = nn.Conv1d(
            channels,
            channels,
            kernel_size,
            padding=padding,
            dilation=dilation,
        )
        self.conv2 = nn.Conv1d(
            channels,
            channels,
            kernel_size,
            padding=padding,
            dilation=dilation,
        )
        self.film = nn.Linear(2, channels * 2)
        self.activation = nn.GELU()

    def forward(self, values: Tensor, condition: Tensor) -> Tensor:
        """Transform one sequence without changing its sample length."""
        hidden = self.conv1(values)
        scale, shift = self.film(condition).chunk(2, dim=1)
        hidden = hidden * (1.0 + scale.unsqueeze(-1)) + shift.unsqueeze(-1)
        hidden = self.activation(hidden)
        hidden = self.conv2(hidden)
        output: Tensor = self.activation(values + hidden)
        return output


class EventProtectedResidualTCN(nn.Module):
    """Predict a bounded residual while forcing truth-event guard samples to zero."""

    def __init__(self, config: ResidualTCNConfig, max_abs_residual_V: float) -> None:
        super().__init__()
        self.input_scale_V = float(config.input_scale_V)
        self.max_abs_residual_V = float(max_abs_residual_V)
        self.input_projection = nn.Conv1d(3, config.hidden_channels, kernel_size=1)
        self.blocks = nn.ModuleList(
            [
                FiLMResidualBlock(
                    config.hidden_channels,
                    config.kernel_size,
                    dilation,
                )
                for dilation in config.dilations
            ]
        )
        self.output_projection = nn.Conv1d(config.hidden_channels, 1, kernel_size=1)

    def forward(
        self,
        physical_waveform_V: Tensor,
        event_guard_mask: Tensor,
        condition: Tensor,
    ) -> Tensor:
        """Return a bounded residual with no write access at protected event samples."""
        if physical_waveform_V.ndim != 3 or physical_waveform_V.shape[1] != 1:
            raise ValueError("physical_waveform_V must have shape [batch, 1, samples]")
        if event_guard_mask.shape != physical_waveform_V.shape:
            raise ValueError("event_guard_mask must match the physical waveform shape")
        if condition.ndim != 2 or condition.shape[1] != 2:
            raise ValueError("condition must have shape [batch, 2]")
        sample_count = physical_waveform_V.shape[-1]
        position = torch.linspace(
            -1.0,
            1.0,
            sample_count,
            dtype=physical_waveform_V.dtype,
            device=physical_waveform_V.device,
        ).expand(physical_waveform_V.shape[0], 1, sample_count)
        inputs = torch.cat(
            (
                physical_waveform_V / self.input_scale_V,
                event_guard_mask,
                position,
            ),
            dim=1,
        )
        hidden = self.input_projection(inputs)
        for block in self.blocks:
            hidden = block(hidden, condition)
        raw = self.output_projection(hidden)
        bounded = torch.tanh(raw) * self.max_abs_residual_V
        return bounded * (1.0 - event_guard_mask)


def normalized_condition(true_rate_cps: Tensor, sample_rate_hz: Tensor) -> Tensor:
    """Map the supported physical domain to stable dimensionless coordinates."""
    log_rate = (torch.log10(true_rate_cps) - 1.0) / 6.0
    sample_rate = (sample_rate_hz - 100.0e6) / 150.0e6
    return torch.stack((log_rate, sample_rate), dim=1)
