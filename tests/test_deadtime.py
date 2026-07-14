from __future__ import annotations

from pathlib import Path

import numpy as np

from he3sim.acquisition.dead_time import apply_dead_time, theoretical_observed_rate_cps
from he3sim.analysis.phase3_validation import validate_phase3_physics
from he3sim.config import DeadTimeMode, load_config

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_nonparalyzable_and_paralyzable_extension_rules() -> None:
    times = np.array([0.0, 0.5, 1.1, 1.4, 2.2])
    nonparalyzable = apply_dead_time(times, 1.0, DeadTimeMode.NONPARALYZABLE)
    paralyzable = apply_dead_time(times, 1.0, DeadTimeMode.PARALYZABLE)

    np.testing.assert_array_equal(nonparalyzable.accepted, [True, False, True, False, True])
    np.testing.assert_array_equal(paralyzable.accepted, [True, False, False, False, False])
    np.testing.assert_array_equal(
        apply_dead_time(times, 0.0, DeadTimeMode.NONE).accepted,
        np.ones(times.size, dtype=np.bool_),
    )


def test_ideal_rate_formulas_and_standard_scan() -> None:
    assert theoretical_observed_rate_cps(1000.0, 1.0e-4, DeadTimeMode.NONPARALYZABLE) == (
        1000.0 / 1.1
    )
    assert np.isclose(
        theoretical_observed_rate_cps(1000.0, 1.0e-4, DeadTimeMode.PARALYZABLE),
        1000.0 * np.exp(-0.1),
    )
    config = load_config(PROJECT_ROOT / "configs" / "demo_minimal.yaml")
    report = validate_phase3_physics(config, replicates=30)
    assert report.passed
    assert len(report.points) == 26
