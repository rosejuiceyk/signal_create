"""Leak-free exact-physics windows and detector encoding for Phase 5."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import torch

from he3sim.config import He3SimConfig, ParameterStatus, ParameterValue
from he3sim.physics.amplitude import LinearAmplitudeMapper
from he3sim.physics.arrivals import PoissonUniformArrivalGenerator
from he3sim.physics.events import event_parameter_status
from he3sim.physics.pulse_parameters import FixedPulseParameterProvider
from he3sim.physics.rate_profiles import ConstantRateProfile
from he3sim.physics.spectra import ParametricHe3Spectrum, SpectrumComponent


def _required_float(parameter: ParameterValue[float], name: str) -> float:
    if parameter.value is None:
        raise ValueError(f"{name} requires an explicit value for Phase 5")
    return float(parameter.value)


def _required_int(parameter: ParameterValue[int], name: str) -> int:
    if parameter.value is None:
        raise ValueError(f"{name} requires an explicit value for Phase 5")
    return int(parameter.value)


@dataclass(frozen=True, slots=True)
class DetectorSpecification:
    """Derived config encoding and hard output supports without invented parameters."""

    encoding: tuple[float, ...]
    component_weights: tuple[float, float, float, float]
    energy_min_keV: tuple[float, float, float, float]
    energy_max_keV: tuple[float, float, float, float]
    energy_initial_logit_mean: tuple[float, float, float, float]
    gain_V_per_keV: float
    offset_V: float
    spread_std_V: float
    tau_r_s: float
    tau_d_s: float
    polarity: int
    parameter_status: ParameterStatus

    def to_dict(self) -> dict[str, Any]:
        """Return a checkpoint-safe primitive representation."""
        return {
            "encoding": list(self.encoding),
            "component_weights": list(self.component_weights),
            "energy_min_keV": list(self.energy_min_keV),
            "energy_max_keV": list(self.energy_max_keV),
            "energy_initial_logit_mean": list(self.energy_initial_logit_mean),
            "gain_V_per_keV": self.gain_V_per_keV,
            "offset_V": self.offset_V,
            "spread_std_V": self.spread_std_V,
            "tau_r_s": self.tau_r_s,
            "tau_d_s": self.tau_d_s,
            "polarity": self.polarity,
            "parameter_status": self.parameter_status.value,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> DetectorSpecification:
        """Restore a detector specification from a trusted local checkpoint."""
        return cls(
            encoding=tuple(float(item) for item in value["encoding"]),
            component_weights=tuple(float(item) for item in value["component_weights"]),  # type: ignore[arg-type]
            energy_min_keV=tuple(float(item) for item in value["energy_min_keV"]),  # type: ignore[arg-type]
            energy_max_keV=tuple(float(item) for item in value["energy_max_keV"]),  # type: ignore[arg-type]
            energy_initial_logit_mean=tuple(
                float(item) for item in value["energy_initial_logit_mean"]
            ),  # type: ignore[arg-type]
            gain_V_per_keV=float(value["gain_V_per_keV"]),
            offset_V=float(value["offset_V"]),
            spread_std_V=float(value["spread_std_V"]),
            tau_r_s=float(value["tau_r_s"]),
            tau_d_s=float(value["tau_d_s"]),
            polarity=int(value["polarity"]),
            parameter_status=ParameterStatus(str(value["parameter_status"])),
        )


def detector_specification(config: He3SimConfig) -> DetectorSpecification:
    """Derive all network supports and encoding values from the governed base config."""
    spectrum = ParametricHe3Spectrum.from_config(config.spectrum)
    amplitude = LinearAmplitudeMapper.from_config(config.amplitude)
    tau_r_s = _required_float(config.pulse_shape.tau_r_s, "tau_r_s")
    tau_d_s = _required_float(config.pulse_shape.tau_d_s, "tau_d_s")
    full_upper = max(
        spectrum.full_energy_keV + 12.0 * spectrum.full_energy_sigma_keV,
        spectrum.full_energy_keV * 1.05,
    )
    component_parameters = (
        (0.0, full_upper, spectrum.full_energy_keV / full_upper),
        (
            spectrum.proton_wall[0],
            spectrum.proton_wall[1],
            spectrum.proton_wall[2] / (spectrum.proton_wall[2] + spectrum.proton_wall[3]),
        ),
        (
            spectrum.triton_wall[0],
            spectrum.triton_wall[1],
            spectrum.triton_wall[2] / (spectrum.triton_wall[2] + spectrum.triton_wall[3]),
        ),
        (
            spectrum.double_wall[0] if spectrum.double_wall is not None else 0.0,
            spectrum.double_wall[1] if spectrum.double_wall is not None else full_upper,
            (
                spectrum.double_wall[2] / (spectrum.double_wall[2] + spectrum.double_wall[3])
                if spectrum.double_wall is not None
                else 0.5
            ),
        ),
    )
    energy_min = tuple(float(item[0]) for item in component_parameters)
    energy_max = tuple(float(item[1]) for item in component_parameters)
    means = tuple(float(np.clip(item[2], 1.0e-4, 1.0 - 1.0e-4)) for item in component_parameters)
    logits = tuple(float(np.log(mean / (1.0 - mean))) for mean in means)
    encoding = (
        *spectrum.weights,
        np.log1p(spectrum.full_energy_keV) / 8.0,
        np.log1p(spectrum.full_energy_sigma_keV) / 5.0,
        np.log(amplitude.gain_V_per_keV) / 12.0,
        amplitude.offset_V,
        np.log1p(amplitude.spread_std_V) / 2.0,
        np.log(tau_r_s) / 20.0,
        np.log(tau_d_s - tau_r_s) / 20.0,
        float(amplitude.polarity),
    )
    return DetectorSpecification(
        encoding=tuple(float(item) for item in encoding),
        component_weights=spectrum.weights,
        energy_min_keV=energy_min,  # type: ignore[arg-type]
        energy_max_keV=energy_max,  # type: ignore[arg-type]
        energy_initial_logit_mean=logits,  # type: ignore[arg-type]
        gain_V_per_keV=amplitude.gain_V_per_keV,
        offset_V=amplitude.offset_V,
        spread_std_V=amplitude.spread_std_V,
        tau_r_s=tau_r_s,
        tau_d_s=tau_d_s,
        polarity=amplitude.polarity,
        parameter_status=event_parameter_status(config),
    )


@dataclass(frozen=True, slots=True)
class EventWindow:
    """One independently generated variable-length exact-physics training window."""

    true_rate_cps: float
    duration_s: float
    times_s: npt.NDArray[np.float64]
    energy_dep_keV: npt.NDArray[np.float64]
    component_id: npt.NDArray[np.int64]
    amplitude_peak_V: npt.NDArray[np.float64]
    tau_r_s: npt.NDArray[np.float64]
    tau_d_s: npt.NDArray[np.float64]

    @property
    def count(self) -> int:
        """Return the realized variable event count."""
        return int(self.times_s.size)


class ExactPhysicsWindowSampler:
    """Create independent Phase 5 targets through the existing exact Phase 1 providers."""

    def __init__(self, config: He3SimConfig) -> None:
        self._arrival = PoissonUniformArrivalGenerator()
        self._spectrum = ParametricHe3Spectrum.from_config(config.spectrum)
        self._amplitude = LinearAmplitudeMapper.from_config(config.amplitude)
        self._pulse = FixedPulseParameterProvider(
            _required_float(config.pulse_shape.tau_r_s, "tau_r_s"),
            _required_float(config.pulse_shape.tau_d_s, "tau_d_s"),
        )

    def sample(
        self,
        true_rate_cps: float,
        duration_s: float,
        rng: np.random.Generator,
        max_events: int,
    ) -> EventWindow:
        """Sample a bounded exact window without crossing dataset splits."""
        times = self._arrival.sample(ConstantRateProfile(true_rate_cps), 0.0, duration_s, rng)
        if times.size > max_events:
            raise ValueError("realized exact window exceeds max_events")
        spectrum = self._spectrum.sample(times.size, rng)
        amplitude = self._amplitude.sample(spectrum.energy_dep_keV, rng)
        pulse = self._pulse.sample(amplitude.amplitude_peak_V, spectrum.component_id, rng)
        return EventWindow(
            true_rate_cps=true_rate_cps,
            duration_s=duration_s,
            times_s=times,
            energy_dep_keV=spectrum.energy_dep_keV,
            component_id=np.asarray(spectrum.component_id, dtype=np.int64),
            amplitude_peak_V=amplitude.amplitude_peak_V,
            tau_r_s=pulse.tau_r_s,
            tau_d_s=pulse.tau_d_s,
        )


def generate_log_uniform_windows(
    sampler: ExactPhysicsWindowSampler,
    *,
    count: int,
    rate_min_cps: float,
    rate_max_cps: float,
    expected_events_min: float,
    expected_events_max: float,
    max_events: int,
    seed: int,
) -> list[EventWindow]:
    """Generate a training split with independent log-uniform rates and window sizes."""
    rng = np.random.default_rng(seed)
    windows: list[EventWindow] = []
    while len(windows) < count:
        rate = float(10.0 ** rng.uniform(np.log10(rate_min_cps), np.log10(rate_max_cps)))
        expected = float(
            10.0 ** rng.uniform(np.log10(expected_events_min), np.log10(expected_events_max))
        )
        try:
            windows.append(sampler.sample(rate, expected / rate, rng, max_events))
        except ValueError:
            continue
    return windows


def generate_fixed_rate_windows(
    sampler: ExactPhysicsWindowSampler,
    rates_cps: Sequence[float],
    *,
    total_windows: int,
    expected_events: float,
    max_events: int,
    seed: int,
) -> list[EventWindow]:
    """Generate a disjoint fixed-rate validation or exact-comparison split."""
    rng = np.random.default_rng(seed)
    windows: list[EventWindow] = []
    for index in range(total_windows):
        rate = float(rates_cps[index % len(rates_cps)])
        windows.append(sampler.sample(rate, expected_events / rate, rng, max_events))
    return windows


@dataclass(frozen=True, slots=True)
class EventBatch:
    """Padded-free flattened event tensors and their parent-window indices."""

    true_rate_cps: torch.Tensor
    duration_s: torch.Tensor
    counts: torch.Tensor
    event_window_index: torch.Tensor
    intervals_s: torch.Tensor
    energy_dep_keV: torch.Tensor
    component_id: torch.Tensor
    amplitude_peak_V: torch.Tensor
    tau_r_s: torch.Tensor
    tau_d_s: torch.Tensor

    def to(self, device: torch.device) -> EventBatch:
        """Move all tensors together without changing variable-length alignment."""
        return EventBatch(
            true_rate_cps=self.true_rate_cps.to(device),
            duration_s=self.duration_s.to(device),
            counts=self.counts.to(device),
            event_window_index=self.event_window_index.to(device),
            intervals_s=self.intervals_s.to(device),
            energy_dep_keV=self.energy_dep_keV.to(device),
            component_id=self.component_id.to(device),
            amplitude_peak_V=self.amplitude_peak_V.to(device),
            tau_r_s=self.tau_r_s.to(device),
            tau_d_s=self.tau_d_s.to(device),
        )


def collate_event_windows(windows: Sequence[EventWindow]) -> EventBatch:
    """Flatten variable-length windows while retaining a parent index per event."""
    if not windows:
        raise ValueError("cannot collate an empty window batch")
    counts = np.asarray([window.count for window in windows], dtype=np.int64)
    parent = np.repeat(np.arange(len(windows), dtype=np.int64), counts)

    def concatenate(name: str, dtype: npt.DTypeLike) -> npt.NDArray[np.generic]:
        arrays = [np.asarray(getattr(window, name), dtype=dtype) for window in windows]
        return np.concatenate(arrays) if arrays else np.empty(0, dtype=dtype)

    interval_arrays = [np.diff(np.concatenate(([0.0], window.times_s))) for window in windows]
    intervals = (
        np.concatenate(interval_arrays) if interval_arrays else np.empty(0, dtype=np.float64)
    )
    return EventBatch(
        true_rate_cps=torch.as_tensor(
            [window.true_rate_cps for window in windows], dtype=torch.float32
        ),
        duration_s=torch.as_tensor([window.duration_s for window in windows], dtype=torch.float32),
        counts=torch.as_tensor(counts, dtype=torch.float32),
        event_window_index=torch.as_tensor(parent, dtype=torch.long),
        intervals_s=torch.as_tensor(intervals, dtype=torch.float32),
        energy_dep_keV=torch.as_tensor(
            concatenate("energy_dep_keV", np.float64), dtype=torch.float32
        ),
        component_id=torch.as_tensor(concatenate("component_id", np.int64), dtype=torch.long),
        amplitude_peak_V=torch.as_tensor(
            concatenate("amplitude_peak_V", np.float64), dtype=torch.float32
        ),
        tau_r_s=torch.as_tensor(concatenate("tau_r_s", np.float64), dtype=torch.float32),
        tau_d_s=torch.as_tensor(concatenate("tau_d_s", np.float64), dtype=torch.float32),
    )


def component_is_supported(specification: DetectorSpecification, component_id: int) -> bool:
    """Return whether the governed base spectrum assigns positive probability."""
    return specification.component_weights[SpectrumComponent(component_id)] > 0.0
