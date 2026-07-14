from __future__ import annotations

import numpy as np
import pytest

from he3sim.random import RandomContext


def test_root_generator_is_reproducible() -> None:
    left = RandomContext(12345).generator.normal(size=16)
    right = RandomContext(12345).generator.normal(size=16)

    np.testing.assert_array_equal(left, right)


def test_different_seeds_produce_different_sequences() -> None:
    left = RandomContext(1).generator.integers(0, 2**31, size=16)
    right = RandomContext(2).generator.integers(0, 2**31, size=16)

    assert not np.array_equal(left, right)


def test_spawned_child_streams_are_reproducible_and_distinct() -> None:
    first_children = RandomContext(9876).spawn(2)
    second_children = RandomContext(9876).spawn(2)
    first_values = [child.random(8) for child in first_children]
    second_values = [child.random(8) for child in second_children]

    np.testing.assert_array_equal(first_values[0], second_values[0])
    np.testing.assert_array_equal(first_values[1], second_values[1])
    assert not np.array_equal(first_values[0], first_values[1])


def test_random_context_rejects_negative_inputs() -> None:
    with pytest.raises(ValueError, match="seed"):
        RandomContext(-1)
    with pytest.raises(ValueError, match="count"):
        RandomContext(1).spawn(-1)


@pytest.mark.parametrize("seed", [True, 1.5, "1", np.nan])
def test_random_context_rejects_non_integer_seeds(seed: object) -> None:
    with pytest.raises(TypeError, match="integer"):
        RandomContext(seed)  # type: ignore[arg-type]
