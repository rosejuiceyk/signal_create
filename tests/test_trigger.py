from __future__ import annotations

import numpy as np

from he3sim.acquisition.trigger import ThresholdTrigger


def test_positive_trigger_hold_and_hysteresis_cross_block() -> None:
    trigger = ThresholdTrigger(10.0, 1, 1.0, 0.2, 0.2)
    first, state = trigger.process_block([0.0, 1.1], 0)
    second, state = trigger.process_block([1.2, 0.9, 0.7, 1.1, 1.2], 2, state)

    assert first.size == 0
    np.testing.assert_array_equal(second, [1, 5])
    assert state.next_sample_index == 7


def test_negative_trigger_uses_signed_threshold() -> None:
    trigger = ThresholdTrigger(100.0, -1, -0.5, 0.1, 0.0)
    candidates, _ = trigger.process_block([0.0, -0.6, -0.7, -0.3, -0.6], 0)

    np.testing.assert_array_equal(candidates, [1, 4])
