"""Source-driven pure-prompt branching-chain arrival generation."""

from __future__ import annotations

import heapq
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from he3sim.physics.arrivals import PoissonUniformArrivalGenerator
from he3sim.physics.protocols import EventArrivalGenerator, RateProfile
from he3sim.physics.source_model import PromptSourceModel


@dataclass(frozen=True, slots=True)
class ChainTraceNode:
    """One completed neutron reaction retained for optional validation figures."""

    neutron_id: int
    parent_id: int
    chain_id: int
    generation: int
    birth_time_s: float
    reaction_time_s: float
    reaction: str
    offspring_count: int


@dataclass(frozen=True, slots=True)
class CorrelatedArrivalBatch:
    """Sorted detections and aligned chain-lineage labels for one time window."""

    times_s: npt.NDArray[np.float64]
    chain_ids: npt.NDArray[np.int64]
    generations: npt.NDArray[np.int32]
    trace_nodes: tuple[ChainTraceNode, ...] = ()

    def __post_init__(self) -> None:
        """Require aligned one-dimensional arrays."""
        shapes = {self.times_s.shape, self.chain_ids.shape, self.generations.shape}
        if len(shapes) != 1 or self.times_s.ndim != 1:
            raise ValueError("correlated arrival arrays must be aligned vectors")


class BranchingChainGenerator:
    """Generate detections from source-driven subcritical prompt neutron chains."""

    def __init__(
        self,
        model: PromptSourceModel,
        source_generator: EventArrivalGenerator | None = None,
        max_events: int = 1_000_000,
        max_chain_generation: int = 128,
        max_total_reactions: int = 1_000_000,
        trace_chain_limit: int = 0,
    ) -> None:
        """Configure the model and fail-fast software resource guards."""
        if max_events <= 0 or max_chain_generation <= 0 or max_total_reactions <= 0:
            raise ValueError("branching-chain safety limits must be positive")
        if trace_chain_limit < 0:
            raise ValueError("trace_chain_limit must be non-negative")
        self.model = model
        self.source_generator = source_generator or PoissonUniformArrivalGenerator()
        self.max_events = max_events
        self.max_chain_generation = max_chain_generation
        self.max_total_reactions = max_total_reactions
        self.trace_chain_limit = trace_chain_limit
        self._pending: list[tuple[float, int, int, int, int, float]] = []
        self._next_chain_id = 0
        self._next_sequence = 0
        self._next_start_s: float | None = None
        self._reaction_count = 0
        self._emitted_count = 0

    def _schedule_neutron(
        self,
        birth_time_s: float,
        chain_id: int,
        generation: int,
        rng: np.random.Generator,
        parent_id: int = -1,
    ) -> int:
        """Schedule one neutron reaction after an exponential lifetime."""
        if generation > self.max_chain_generation:
            raise ValueError("branching chain exceeded max_chain_generation")
        reaction_time_s = birth_time_s + float(rng.exponential(1.0 / self.model.lambda_t_per_s))
        neutron_id = self._next_sequence
        heapq.heappush(
            self._pending,
            (reaction_time_s, neutron_id, chain_id, generation, parent_id, birth_time_s),
        )
        self._next_sequence += 1
        return neutron_id

    def sample_with_lineage(
        self,
        profile: RateProfile,
        t_start_s: float,
        duration_s: float,
        rng: np.random.Generator,
    ) -> CorrelatedArrivalBatch:
        """Return detections in one ordered, contiguous source-on observation window."""
        if not np.isfinite(t_start_s):
            raise ValueError("t_start_s must be finite")
        if not np.isfinite(duration_s) or duration_s <= 0.0:
            raise ValueError("duration_s must be finite and positive")
        stop_s = t_start_s + duration_s
        if not np.isfinite(stop_s) or stop_s <= t_start_s:
            raise ValueError("arrival window must be finite and representable")
        if self._next_start_s is not None and not np.isclose(
            t_start_s, self._next_start_s, rtol=0.0, atol=1.0e-15
        ):
            raise ValueError("branching-chain sampling windows must be contiguous and ordered")

        source_times = self.source_generator.sample(profile, t_start_s, duration_s, rng)
        for source_time_s in source_times:
            chain_id = self._next_chain_id
            self._next_chain_id += 1
            self._schedule_neutron(float(source_time_s), chain_id, 0, rng)

        detection_times: list[float] = []
        chain_ids: list[int] = []
        generations: list[int] = []
        trace_nodes: list[ChainTraceNode] = []
        fission_boundary = self.model.lambda_f_per_s
        capture_boundary = fission_boundary + self.model.lambda_c_per_s

        while self._pending and self._pending[0][0] < stop_s:
            (
                reaction_time_s,
                neutron_id,
                chain_id,
                generation,
                parent_id,
                birth_time_s,
            ) = heapq.heappop(self._pending)
            self._reaction_count += 1
            if self._reaction_count > self.max_total_reactions:
                raise ValueError("branching process exceeded max_total_reactions")
            reaction_draw = float(rng.random()) * self.model.lambda_t_per_s
            reaction = "capture"
            offspring_count = 0
            if reaction_draw < fission_boundary:
                multiplicity = int(rng.choice(self.model.nu_pmf.size, p=self.model.nu_pmf))
                reaction = "fission"
                offspring_count = multiplicity
                child_generation = generation + 1
                if multiplicity and child_generation > self.max_chain_generation:
                    raise ValueError("branching chain exceeded max_chain_generation")
                for _ in range(multiplicity):
                    self._schedule_neutron(
                        reaction_time_s,
                        chain_id,
                        child_generation,
                        rng,
                        parent_id=neutron_id,
                    )
            elif reaction_draw >= capture_boundary:
                reaction = "detection"
                detection_times.append(reaction_time_s)
                chain_ids.append(chain_id)
                generations.append(generation)
                self._emitted_count += 1
                if self._emitted_count > self.max_events:
                    raise ValueError("branching process exceeded the explicit event limit")
            if chain_id < self.trace_chain_limit:
                trace_nodes.append(
                    ChainTraceNode(
                        neutron_id=neutron_id,
                        parent_id=parent_id,
                        chain_id=chain_id,
                        generation=generation,
                        birth_time_s=birth_time_s,
                        reaction_time_s=reaction_time_s,
                        reaction=reaction,
                        offspring_count=offspring_count,
                    )
                )

        self._next_start_s = stop_s
        times = np.asarray(detection_times, dtype=np.float64)
        chains = np.asarray(chain_ids, dtype=np.int64)
        generation_array = np.asarray(generations, dtype=np.int32)
        if times.size and np.any(np.diff(times) <= 0.0):
            raise RuntimeError("correlated arrival times are not strictly increasing")
        return CorrelatedArrivalBatch(times, chains, generation_array, tuple(trace_nodes))

    def sample(
        self,
        profile: RateProfile,
        t_start_s: float,
        duration_s: float,
        rng: np.random.Generator,
    ) -> npt.NDArray[np.float64]:
        """Implement EventArrivalGenerator while retaining lineage internally."""
        return self.sample_with_lineage(profile, t_start_s, duration_s, rng).times_s
