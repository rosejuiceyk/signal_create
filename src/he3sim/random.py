"""Reproducible NumPy random-number contexts."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(slots=True)
class RandomContext:
    """Own a root seed, generator, and deterministic child-stream factory."""

    seed: int
    seed_sequence: np.random.SeedSequence = field(init=False, repr=False)
    generator: np.random.Generator = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Create the root generator without touching NumPy global state."""
        if isinstance(self.seed, bool) or not isinstance(self.seed, (int, np.integer)):
            raise TypeError("seed must be an integer")
        self.seed = int(self.seed)
        if self.seed < 0:
            raise ValueError("seed must be non-negative")
        self.seed_sequence = np.random.SeedSequence(self.seed)
        self.generator = np.random.default_rng(self.seed_sequence)

    def spawn(self, count: int) -> tuple[np.random.Generator, ...]:
        """Create deterministic child generators suitable for future workers."""
        if count < 0:
            raise ValueError("count must be non-negative")
        return tuple(np.random.default_rng(child) for child in self.seed_sequence.spawn(count))
