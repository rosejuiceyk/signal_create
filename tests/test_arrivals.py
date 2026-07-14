from __future__ import annotations

import numpy as np
import pytest

from he3sim.analysis.counting_stats import validate_arrival_algorithms
from he3sim.physics.arrivals import (
    ArrivalAlgorithm,
    CumulativeExponentialArrivalGenerator,
    PoissonUniformArrivalGenerator,
)
from he3sim.physics.rate_profiles import ConstantRateProfile


@pytest.mark.parametrize(
    "generator",
    [PoissonUniformArrivalGenerator(), CumulativeExponentialArrivalGenerator(chunk_size=128)],
)
def test_arrival_times_are_reproducible_ordered_and_in_window(generator: object) -> None:
    profile = ConstantRateProfile(2_000.0)
    first = generator.sample(profile, 1.25, 0.1, np.random.default_rng(123))  # type: ignore[attr-defined]
    second = generator.sample(profile, 1.25, 0.1, np.random.default_rng(123))  # type: ignore[attr-defined]

    np.testing.assert_array_equal(first, second)
    assert np.all(first >= 1.25)
    assert np.all(first < 1.35)
    assert np.all(np.diff(first) > 0.0)


@pytest.mark.parametrize(
    "generator",
    [PoissonUniformArrivalGenerator(), CumulativeExponentialArrivalGenerator(chunk_size=128)],
)
def test_different_seeds_produce_different_arrival_samples(generator: object) -> None:
    profile = ConstantRateProfile(2_000.0)
    first = generator.sample(profile, 0.0, 0.1, np.random.default_rng(1))  # type: ignore[attr-defined]
    second = generator.sample(profile, 0.0, 0.1, np.random.default_rng(2))  # type: ignore[attr-defined]

    assert not np.array_equal(first, second)


@pytest.mark.parametrize(
    "generator",
    [PoissonUniformArrivalGenerator(), CumulativeExponentialArrivalGenerator(chunk_size=64)],
)
def test_extremely_short_low_rate_window_may_be_empty(generator: object) -> None:
    result = generator.sample(  # type: ignore[attr-defined]
        ConstantRateProfile(10.0),
        0.0,
        1.0e-9,
        np.random.default_rng(123),
    )

    assert result.shape == (0,)
    assert result.dtype == np.float64


def test_poisson_count_mean_and_fano_are_stable() -> None:
    generator = PoissonUniformArrivalGenerator()
    profile = ConstantRateProfile(500.0)
    rng = np.random.default_rng(456)
    counts = np.array(
        [generator.sample(profile, 0.0, 0.04, rng).size for _ in range(2_000)],
        dtype=np.float64,
    )

    assert np.mean(counts) == pytest.approx(20.0, rel=0.02)
    assert np.var(counts, ddof=1) / np.mean(counts) == pytest.approx(1.0, abs=0.08)


def test_both_algorithms_pass_deterministic_statistical_validation() -> None:
    artifacts = validate_arrival_algorithms(
        true_rate_cps=1_000.0,
        configured_duration_s=0.01,
        seed=20260713,
        replicates=300,
    )

    assert artifacts.report.passed
    assert set(artifacts.report.algorithms) == {algorithm.value for algorithm in ArrivalAlgorithm}
    assert (
        artifacts.report.interval_two_sample_ks_distance
        <= artifacts.report.interval_two_sample_ks_tolerance
    )


@pytest.mark.parametrize(
    ("true_rate_cps", "seed"),
    [(10.0, 110), (1.0e3, 111), (1.0e5, 112), (1.0e7, 113)],
)
def test_statistical_validation_across_supported_rate_range(
    true_rate_cps: float,
    seed: int,
) -> None:
    artifacts = validate_arrival_algorithms(
        true_rate_cps=true_rate_cps,
        configured_duration_s=200.0 / true_rate_cps,
        seed=seed,
        replicates=500,
    )

    assert artifacts.report.expected_count == pytest.approx(200.0)
    assert artifacts.report.passed
    for statistics in artifacts.report.algorithms.values():
        assert statistics.interval_sample_size > 95_000
        assert statistics.interval_mean_s == pytest.approx(1.0 / true_rate_cps, rel=0.02)
        assert statistics.exponential_ks_distance <= statistics.exponential_ks_distance_tolerance


def test_arrival_generators_reject_nonconstant_profiles() -> None:
    class UnsupportedProfile:
        def rate(self, t_s: float | np.ndarray) -> float | np.ndarray:
            return np.asarray(t_s) + 1.0

    with pytest.raises(TypeError, match="ConstantRateProfile"):
        PoissonUniformArrivalGenerator().sample(
            UnsupportedProfile(),  # type: ignore[arg-type]
            0.0,
            1.0,
            np.random.default_rng(1),
        )


@pytest.mark.parametrize("rate_cps", [0.0, -1.0, 9.999, 1.0e7 + 1.0, np.nan, np.inf, -np.inf])
def test_constant_rate_profile_rejects_invalid_or_unsupported_rates(rate_cps: float) -> None:
    with pytest.raises(ValueError, match="rate_cps"):
        ConstantRateProfile(rate_cps)


@pytest.mark.parametrize("duration_s", [0.0, -1.0, np.nan, np.inf, -np.inf])
def test_arrival_generators_reject_invalid_durations(duration_s: float) -> None:
    with pytest.raises(ValueError, match="duration_s"):
        PoissonUniformArrivalGenerator().sample(
            ConstantRateProfile(10.0),
            0.0,
            duration_s,
            np.random.default_rng(1),
        )


def test_arrival_generator_rejects_unrepresentable_window() -> None:
    with pytest.raises(ValueError, match="representable"):
        PoissonUniformArrivalGenerator().sample(
            ConstantRateProfile(10.0),
            1.0e308,
            1.0,
            np.random.default_rng(1),
        )
