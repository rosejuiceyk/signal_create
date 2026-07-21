"""Split Phase A correlated detections into two simulated detector channels."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from he3sim.config import He3SimConfig, SourceModelKind
from he3sim.physics.chains import CorrelatedArrivalBatch
from he3sim.physics.events import simulate_true_events


@dataclass(frozen=True, slots=True)
class DualDetectorEvents:
    """Detection times, chain IDs, and generations for two independent channels."""

    ch1_times_s: npt.NDArray[np.float64]
    ch1_chain_ids: npt.NDArray[np.int64]
    ch1_generations: npt.NDArray[np.int32]
    ch2_times_s: npt.NDArray[np.float64]
    ch2_chain_ids: npt.NDArray[np.int64]
    ch2_generations: npt.NDArray[np.int32]
    duration_s: float
    source_seed: int


def split_detections(
    events: CorrelatedArrivalBatch,
    efficiency_ch1: float,
    efficiency_ch2: float,
    rng: np.random.Generator,
) -> DualDetectorEvents:
    """Assign each detection to channel 1, channel 2, or neither.

    A detection is assigned to ch1 with probability proportional to
    ``efficiency_ch1``, to ch2 with ``efficiency_ch2``.  Detections not
    assigned to either channel are dropped.
    """
    total_efficiency = efficiency_ch1 + efficiency_ch2
    if not (0.0 < total_efficiency <= 1.0):
        raise ValueError("channel efficiencies must sum to a value in (0, 1]")
    if events.times_s.size == 0:
        return DualDetectorEvents(
            ch1_times_s=np.empty(0, dtype=np.float64),
            ch1_chain_ids=np.empty(0, dtype=np.int64),
            ch1_generations=np.empty(0, dtype=np.int32),
            ch2_times_s=np.empty(0, dtype=np.float64),
            ch2_chain_ids=np.empty(0, dtype=np.int64),
            ch2_generations=np.empty(0, dtype=np.int32),
            duration_s=0.0,
            source_seed=0,
        )
    uniform = rng.random(events.times_s.size)
    p1 = efficiency_ch1 / total_efficiency
    ch1_mask = uniform < p1
    ch2_mask = uniform >= p1
    ch1_times = events.times_s[ch1_mask]
    ch2_times = events.times_s[ch2_mask]
    order1: npt.NDArray[np.intp] = (
        np.argsort(ch1_times) if ch1_times.size else np.array([], dtype=np.intp)
    )
    order2: npt.NDArray[np.intp] = (
        np.argsort(ch2_times) if ch2_times.size else np.array([], dtype=np.intp)
    )
    return DualDetectorEvents(
        ch1_times_s=ch1_times[order1] if order1.size else ch1_times,
        ch1_chain_ids=events.chain_ids[ch1_mask][order1]
        if order1.size
        else events.chain_ids[ch1_mask],
        ch1_generations=events.generations[ch1_mask][order1]
        if order1.size
        else events.generations[ch1_mask],
        ch2_times_s=ch2_times[order2] if order2.size else ch2_times,
        ch2_chain_ids=events.chain_ids[ch2_mask][order2]
        if order2.size
        else events.chain_ids[ch2_mask],
        ch2_generations=events.generations[ch2_mask][order2]
        if order2.size
        else events.generations[ch2_mask],
        duration_s=0.0,
        source_seed=0,
    )


def generate_correlated_times(
    config: He3SimConfig,
    *,
    seed_override: int | None = None,
) -> tuple[npt.NDArray[np.float64], float]:
    """Generate correlated detection times for a single synthetic operating point.

    Uses the config's existing observation duration directly; the caller is
    responsible for setting it appropriately.
    """
    source = config.source_model
    if source.kind is not SourceModelKind.CORRELATED:
        raise ValueError("source_model.kind must be 'correlated'")
    if config.metadata.seed.value is None:
        raise ValueError("config requires a seed")
    seed = seed_override if seed_override is not None else int(config.metadata.seed.value)
    rate = config.simulation.true_rate_cps.value
    if rate is None:
        raise ValueError("true_rate_cps requires a value")
    duration_s = config.observation.duration_s
    if duration_s is None or duration_s.value is None:
        raise ValueError("observation.duration_s requires an explicit value")
    duration = float(duration_s.value)
    target_events = int(rate * duration)
    raw = config.model_dump(mode="python")
    raw["metadata"]["seed"]["value"] = seed
    adjusted = He3SimConfig.model_validate(raw)
    maximum_events = max(target_events * 2, int(np.ceil(target_events / 0.01)))
    simulation = simulate_true_events(
        adjusted,
        max_expected_events=maximum_events,
        source_model=SourceModelKind.CORRELATED,
    )
    times = simulation.events["t_s"].astype(np.float64, copy=False)
    return times, simulation.duration_s
