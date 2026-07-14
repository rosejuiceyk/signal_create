"""Exact block-wise homogeneous-Poisson truth-event streaming for Phase 3."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from he3sim.config import He3SimConfig
from he3sim.physics.amplitude import LinearAmplitudeMapper
from he3sim.physics.events import event_parameter_status
from he3sim.physics.pulse_parameters import FixedPulseParameterProvider
from he3sim.physics.spectra import ParametricHe3Spectrum
from he3sim.random import RandomContext
from he3sim.types import TRUE_EVENT_DTYPE


def _value(value: float | int | None, name: str) -> float:
    if value is None:
        raise ValueError(f"{name} requires an explicit value for event streaming")
    return float(value)


class StreamingTrueEventGenerator:
    """Generate exact independent-increment Poisson chunks with aligned marks."""

    def __init__(
        self,
        config: He3SimConfig,
        max_events: int,
        max_chunk_events: int = 32_768,
    ) -> None:
        """Construct stable child RNG streams and mark providers."""
        if max_events <= 0:
            raise ValueError("max_events must be positive")
        if max_chunk_events <= 0:
            raise ValueError("max_chunk_events must be positive")
        if config.metadata.seed.value is None:
            raise ValueError("seed requires an explicit value")
        self.config = config
        self.max_events = max_events
        self.max_chunk_events = max_chunk_events
        rngs = RandomContext(config.metadata.seed.value).spawn(4)
        self._arrival_rng = rngs[0]
        self._spectrum_rng = rngs[1]
        self._amplitude_rng = rngs[2]
        self._pulse_rng = rngs[3]
        self._spectrum = ParametricHe3Spectrum.from_config(config.spectrum)
        self._amplitude = LinearAmplitudeMapper.from_config(config.amplitude)
        self._pulse = FixedPulseParameterProvider(
            _value(config.pulse_shape.tau_r_s.value, "tau_r_s"),
            _value(config.pulse_shape.tau_d_s.value, "tau_d_s"),
        )
        self._rate_cps = _value(config.simulation.true_rate_cps.value, "true_rate_cps")
        self._next_event_id = 0
        self._next_pileup_group_id = 0
        self._previous_t_s: float | None = None
        self._previous_tau_d_s: float | None = None
        self._next_interval_start_s = 0.0

    @property
    def event_count(self) -> int:
        """Return the number of truth records emitted so far."""
        return self._next_event_id

    def sample_interval(
        self,
        start_s: float,
        stop_s: float,
        sample_rate_hz: float | None = None,
        block_size: int | None = None,
    ) -> npt.NDArray[np.void]:
        """Generate one consecutive interval and optionally map it to waveform samples."""
        if not np.isclose(start_s, self._next_interval_start_s, rtol=0.0, atol=1.0e-15):
            raise ValueError("streaming event intervals must be contiguous and ordered")
        if not np.isfinite(stop_s) or stop_s <= start_s:
            raise ValueError("streaming event interval must have positive finite width")
        duration_s = stop_s - start_s
        count = int(self._arrival_rng.poisson(self._rate_cps * duration_s))
        if count > self.max_chunk_events:
            raise ValueError(
                f"realized event chunk {count} exceeds the explicit chunk limit "
                f"{self.max_chunk_events}; shorten the time or waveform block"
            )
        if self._next_event_id + count > self.max_events:
            raise ValueError("realized streaming event count exceeds the explicit limit")
        times_s = np.sort(self._arrival_rng.uniform(start_s, stop_s, size=count)).astype(
            np.float64, copy=False
        )
        spectrum = self._spectrum.sample(count, self._spectrum_rng)
        amplitudes = self._amplitude.sample(spectrum.energy_dep_keV, self._amplitude_rng)
        pulse = self._pulse.sample(
            amplitudes.amplitude_peak_V,
            spectrum.component_id,
            self._pulse_rng,
        )
        events = np.empty(count, dtype=TRUE_EVENT_DTYPE)
        events["event_id"] = np.arange(
            self._next_event_id,
            self._next_event_id + count,
            dtype=np.int64,
        )
        events["t_s"] = times_s
        events["energy_dep_keV"] = spectrum.energy_dep_keV
        events["spectrum_component_id"] = spectrum.component_id
        events["amplitude_peak_V"] = amplitudes.amplitude_peak_V
        events["tau_r_s"] = pulse.tau_r_s
        events["tau_d_s"] = pulse.tau_d_s
        events["polarity"] = amplitudes.polarity
        events["block_id"] = -1
        events["sample_index"] = -1
        events["parameter_status"] = event_parameter_status(self.config).value.encode("ascii")
        if sample_rate_hz is not None or block_size is not None:
            if sample_rate_hz is None or block_size is None:
                raise ValueError("waveform mapping requires sample_rate_hz and block_size together")
            sample_indices = np.ceil(times_s * sample_rate_hz).astype(np.int64)
            events["sample_index"] = sample_indices
            events["block_id"] = sample_indices // block_size

        for index in range(count):
            time_s = float(events["t_s"][index])
            tau_d_s = float(events["tau_d_s"][index])
            if self._previous_t_s is None:
                group_id = self._next_pileup_group_id
            else:
                assert self._previous_tau_d_s is not None
                separation_s = time_s - self._previous_t_s
                if separation_s > max(self._previous_tau_d_s, tau_d_s):
                    self._next_pileup_group_id += 1
                group_id = self._next_pileup_group_id
            events["pileup_group_id"][index] = group_id
            self._previous_t_s = time_s
            self._previous_tau_d_s = tau_d_s
        self._next_event_id += count
        self._next_interval_start_s = stop_s
        return events
