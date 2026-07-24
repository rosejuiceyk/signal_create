"""Reference and recursive double-exponential waveform renderers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

import numpy as np
import numpy.typing as npt

from he3sim.config import WaveformRenderer
from he3sim.physics.pulse_models import (
    discrete_peak_raw_value,
    validate_time_constants,
    warn_if_time_constants_under_resolved,
)
from he3sim.types import TRUE_EVENT_DTYPE

EventArray = npt.NDArray[np.void]


def waveform_sample_count(duration_s: float, sample_rate_hz: float) -> int:
    """Return a grid containing time zero and one sample at or beyond the event horizon."""
    if not math.isfinite(duration_s) or duration_s <= 0.0:
        raise ValueError("duration_s must be finite and positive")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("sample_rate_hz must be finite and positive")
    count = math.ceil(duration_s * sample_rate_hz) + 1
    if count > np.iinfo(np.int64).max:
        raise ValueError("waveform sample count cannot be represented as int64")
    return count


def event_first_sample_indices(
    event_times_s: npt.NDArray[np.float64],
    sample_rate_hz: float,
) -> npt.NDArray[np.int64]:
    """Map each event to its first causal sample on the time-zero grid."""
    times = np.asarray(event_times_s, dtype=np.float64)
    if times.ndim != 1 or np.any(~np.isfinite(times)):
        raise ValueError("event times must be a finite one-dimensional array")
    if np.any(times < 0.0):
        raise ValueError("event times must be non-negative")
    scaled = times * sample_rate_hz
    if np.any(scaled > np.iinfo(np.int64).max):
        raise ValueError("event sample index cannot be represented as int64")
    return cast(npt.NDArray[np.int64], np.ceil(scaled).astype(np.int64))


def _validate_events(events: EventArray) -> None:
    """Validate the truth fields needed for waveform synthesis."""
    if events.ndim != 1 or events.dtype != TRUE_EVENT_DTYPE:
        raise ValueError("events must be a one-dimensional TRUE_EVENT_DTYPE array")
    if events.size == 0:
        return
    if np.any(~np.isfinite(events["t_s"])) or np.any(events["t_s"] < 0.0):
        raise ValueError("event times must be finite and non-negative")
    if np.any(~np.isfinite(events["amplitude_peak_V"])) or np.any(
        events["amplitude_peak_V"] <= 0.0
    ):
        raise ValueError("event amplitudes must be finite and positive")
    if not set(np.unique(events["polarity"]).tolist()) <= {-1, 1}:
        raise ValueError("event polarities must be -1 or 1")
    if np.any(~np.isfinite(events["tau_r_s"])) or np.any(~np.isfinite(events["tau_d_s"])):
        raise ValueError("event time constants must be finite")
    if np.any(events["tau_r_s"] <= 0.0) or np.any(events["tau_d_s"] <= events["tau_r_s"]):
        raise ValueError("event time constants must satisfy tau_d_s > tau_r_s > 0")


def render_direct_sparse(
    events: EventArray,
    sample_count: int,
    sample_rate_hz: float,
) -> npt.NDArray[np.float64]:
    """Render every truth event by directly adding its sampled causal pulse."""
    return render_direct_sparse_block(events, 0, sample_count, sample_rate_hz)


def render_direct_sparse_block(
    events: EventArray,
    sample_start: int,
    sample_count: int,
    sample_rate_hz: float,
) -> npt.NDArray[np.float64]:
    """Render a bounded global-grid slice by direct per-event summation."""
    _validate_events(events)
    if sample_start < 0 or sample_count <= 0:
        raise ValueError("sample_start must be non-negative and sample_count positive")
    if events.size:
        time_constant_pairs = np.unique(
            np.column_stack((events["tau_r_s"], events["tau_d_s"])),
            axis=0,
        )
        for tau_r_s, tau_d_s in time_constant_pairs:
            warn_if_time_constants_under_resolved(
                sample_rate_hz,
                float(tau_r_s),
                float(tau_d_s),
            )
    sample_stop = sample_start + sample_count
    samples = np.zeros(sample_count, dtype=np.float64)
    for event in events:
        event_time_s = float(event["t_s"])
        tau_r_s = float(event["tau_r_s"])
        tau_d_s = float(event["tau_d_s"])
        event_first_index = math.ceil(event_time_s * sample_rate_hz)
        first_index = max(sample_start, event_first_index)
        if first_index >= sample_stop:
            continue
        raw_peak = discrete_peak_raw_value(
            event_time_s,
            sample_rate_hz,
            tau_r_s,
            tau_d_s,
        )
        sample_indices = np.arange(first_index, sample_stop, dtype=np.float64)
        delays_s = sample_indices / sample_rate_hz - event_time_s
        raw_kernel = np.exp(-delays_s / tau_d_s) - np.exp(-delays_s / tau_r_s)
        signed_amplitude_V = float(event["amplitude_peak_V"]) * int(event["polarity"])
        samples[first_index - sample_start :] += signed_amplitude_V * raw_kernel / raw_peak
    return samples


@dataclass(frozen=True, slots=True)
class RecursiveFixedTauState:
    """Two exponential states immediately after the previous rendered sample."""

    next_sample_index: int = 0
    decay_state_V: float = 0.0
    rise_state_V: float = 0.0

    def __post_init__(self) -> None:
        """Reject invalid state values before they cross a block boundary."""
        if self.next_sample_index < 0:
            raise ValueError("next_sample_index must be non-negative")
        if not math.isfinite(self.decay_state_V) or not math.isfinite(self.rise_state_V):
            raise ValueError("recursive states must be finite")


class RecursiveFixedTauRenderer:
    """O(samples + events) renderer with explicit cross-block state."""

    def __init__(self, sample_rate_hz: float, tau_r_s: float, tau_d_s: float) -> None:
        """Precompute fixed per-sample exponential decay factors."""
        validate_time_constants(tau_r_s, tau_d_s)
        if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
            raise ValueError("sample_rate_hz must be finite and positive")
        warn_if_time_constants_under_resolved(sample_rate_hz, tau_r_s, tau_d_s)
        self.sample_rate_hz = sample_rate_hz
        self.tau_r_s = tau_r_s
        self.tau_d_s = tau_d_s
        self._rise_decay = math.exp(-1.0 / (sample_rate_hz * tau_r_s))
        self._decay_decay = math.exp(-1.0 / (sample_rate_hz * tau_d_s))

    @classmethod
    def from_events(
        cls,
        events: EventArray,
        sample_rate_hz: float,
        fallback_tau_r_s: float | None = None,
        fallback_tau_d_s: float | None = None,
    ) -> RecursiveFixedTauRenderer:
        """Construct from fixed event constants, using fallbacks only for an empty table."""
        _validate_events(events)
        if events.size:
            tau_r_s = float(events["tau_r_s"][0])
            tau_d_s = float(events["tau_d_s"][0])
            if not np.allclose(events["tau_r_s"], tau_r_s, rtol=1.0e-12, atol=0.0):
                raise ValueError("recursive_fixed_tau requires one shared tau_r_s")
            if not np.allclose(events["tau_d_s"], tau_d_s, rtol=1.0e-12, atol=0.0):
                raise ValueError("recursive_fixed_tau requires one shared tau_d_s")
        else:
            if fallback_tau_r_s is None or fallback_tau_d_s is None:
                raise ValueError("empty event tables require fallback time constants")
            tau_r_s = fallback_tau_r_s
            tau_d_s = fallback_tau_d_s
        return cls(sample_rate_hz, tau_r_s, tau_d_s)

    def render_block(
        self,
        events: EventArray,
        sample_start: int,
        sample_count: int,
        state: RecursiveFixedTauState | None = None,
    ) -> tuple[npt.NDArray[np.float64], RecursiveFixedTauState, int]:
        """Render one contiguous block and return samples, new state, and injected count."""
        _validate_events(events)
        if sample_start < 0 or sample_count <= 0:
            raise ValueError("sample_start must be non-negative and sample_count positive")
        current_state = state or RecursiveFixedTauState()
        if current_state.next_sample_index != sample_start:
            raise ValueError("recursive blocks must be contiguous and ordered")
        if events.size:
            if not np.allclose(events["tau_r_s"], self.tau_r_s, rtol=1.0e-12, atol=0.0):
                raise ValueError("recursive_fixed_tau requires one shared tau_r_s")
            if not np.allclose(events["tau_d_s"], self.tau_d_s, rtol=1.0e-12, atol=0.0):
                raise ValueError("recursive_fixed_tau requires one shared tau_d_s")

        sample_stop = sample_start + sample_count
        first_indices = event_first_sample_indices(events["t_s"], self.sample_rate_hz)
        selected = (first_indices >= sample_start) & (first_indices < sample_stop)
        selected_indices = first_indices[selected]
        selected_events = events[selected]
        decay_sources = np.zeros(sample_count, dtype=np.float64)
        rise_sources = np.zeros(sample_count, dtype=np.float64)

        for event, first_index in zip(selected_events, selected_indices, strict=True):
            event_time_s = float(event["t_s"])
            raw_peak = discrete_peak_raw_value(
                event_time_s,
                self.sample_rate_hz,
                self.tau_r_s,
                self.tau_d_s,
            )
            signed_amplitude_V = float(event["amplitude_peak_V"]) * int(event["polarity"])
            coefficient_V = signed_amplitude_V / raw_peak
            delay_s = first_index / self.sample_rate_hz - event_time_s
            local_index = int(first_index - sample_start)
            decay_sources[local_index] += coefficient_V * math.exp(-delay_s / self.tau_d_s)
            rise_sources[local_index] += coefficient_V * math.exp(-delay_s / self.tau_r_s)

        output = np.empty(sample_count, dtype=np.float64)
        decay_state = current_state.decay_state_V
        rise_state = current_state.rise_state_V
        for index in range(sample_count):
            decay_state = self._decay_decay * decay_state + decay_sources[index]
            rise_state = self._rise_decay * rise_state + rise_sources[index]
            output[index] = decay_state - rise_state

        next_state = RecursiveFixedTauState(
            next_sample_index=sample_stop,
            decay_state_V=decay_state,
            rise_state_V=rise_state,
        )
        return output, next_state, int(np.count_nonzero(selected))


def render_recursive_fixed_tau(
    events: EventArray,
    sample_count: int,
    sample_rate_hz: float,
    fallback_tau_r_s: float | None = None,
    fallback_tau_d_s: float | None = None,
) -> npt.NDArray[np.float64]:
    """Render a complete waveform using the fixed-time-constant recurrence."""
    renderer = RecursiveFixedTauRenderer.from_events(
        events,
        sample_rate_hz,
        fallback_tau_r_s,
        fallback_tau_d_s,
    )
    output, _, injected_count = renderer.render_block(events, 0, sample_count)
    expected_injected = int(
        np.count_nonzero(event_first_sample_indices(events["t_s"], sample_rate_hz) < sample_count)
    )
    if injected_count != expected_injected:
        raise RuntimeError("not every in-range truth event was injected into the waveform")
    return output


def resolve_renderer_backend(events: EventArray, requested: WaveformRenderer) -> WaveformRenderer:
    """Select the recursive backend for fixed constants and otherwise use the reference."""
    if requested is not WaveformRenderer.AUTO:
        return requested
    if events.size <= 1:
        return WaveformRenderer.RECURSIVE_FIXED_TAU
    fixed_rise = np.allclose(events["tau_r_s"], events["tau_r_s"][0], rtol=1.0e-12, atol=0.0)
    fixed_decay = np.allclose(events["tau_d_s"], events["tau_d_s"][0], rtol=1.0e-12, atol=0.0)
    if fixed_rise and fixed_decay:
        return WaveformRenderer.RECURSIVE_FIXED_TAU
    return WaveformRenderer.DIRECT_SPARSE
