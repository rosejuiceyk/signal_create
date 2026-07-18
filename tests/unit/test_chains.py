from __future__ import annotations

import numpy as np
import pytest

from he3sim.config import ParameterStatus, ParameterValue, SourceModelConfig
from he3sim.physics.chains import BranchingChainGenerator
from he3sim.physics.rate_profiles import ConstantRateProfile
from he3sim.physics.source_model import PromptSourceModel


def parameter(value: float | list[float]) -> ParameterValue[float] | ParameterValue[list[float]]:
    return ParameterValue(value=value, status=ParameterStatus.SYNTHETIC_DEMO)


def prompt_model(
    k_eff: float,
    source_rate_cps: float,
    epsilon: float = 0.1,
    alpha: float = 1_000.0,
) -> PromptSourceModel:
    config = SourceModelConfig(
        kind="correlated",
        k_eff=parameter(k_eff),  # type: ignore[arg-type]
        alpha=parameter(alpha),  # type: ignore[arg-type]
        detection_efficiency=parameter(epsilon),  # type: ignore[arg-type]
        nu_bar=parameter(2.5),  # type: ignore[arg-type]
        nu_pmf=parameter([0.0, 0.0, 0.5, 0.5]),  # type: ignore[arg-type]
        source_rate_cps=parameter(source_rate_cps),  # type: ignore[arg-type]
    )
    return PromptSourceModel.from_config(config)


def sample_count(model: PromptSourceModel, duration_s: float, seed: int) -> int:
    generator = BranchingChainGenerator(model, max_total_reactions=2_000_000)
    profile = ConstantRateProfile(model.source_rate_cps)
    return generator.sample(profile, 0.0, duration_s, np.random.default_rng(seed)).size


def test_correlated_arrivals_are_reproducible_ordered_and_lineage_aligned() -> None:
    model = prompt_model(0.2, 8_000.0)
    profile = ConstantRateProfile(model.source_rate_cps)
    left = BranchingChainGenerator(model).sample_with_lineage(
        profile, 0.0, 0.1, np.random.default_rng(123)
    )
    right = BranchingChainGenerator(model).sample_with_lineage(
        profile, 0.0, 0.1, np.random.default_rng(123)
    )

    np.testing.assert_array_equal(left.times_s, right.times_s)
    np.testing.assert_array_equal(left.chain_ids, right.chain_ids)
    np.testing.assert_array_equal(left.generations, right.generations)
    assert np.all(left.times_s >= 0.0)
    assert np.all(left.times_s < 0.1)
    assert np.all(np.diff(left.times_s) > 0.0)
    assert left.times_s.shape == left.chain_ids.shape == left.generations.shape
    assert np.all(left.chain_ids >= 0)
    assert np.all(left.generations >= 0)


def test_long_window_mean_rate_matches_analytic_first_moment() -> None:
    model = prompt_model(0.2, 8_000.0)

    count = sample_count(model, duration_s=30.0, seed=456)

    assert count / 30.0 == pytest.approx(model.expected_detected_rate_cps, rel=0.02)


def test_near_zero_multiplication_degenerates_to_poisson_counts() -> None:
    model = prompt_model(1.0e-9, 1_000.0, epsilon=0.2, alpha=10_000.0)
    counts = np.asarray(
        [sample_count(model, duration_s=0.1, seed=seed) for seed in range(500)],
        dtype=np.float64,
    )

    assert np.mean(counts) == pytest.approx(20.0, rel=0.03)
    assert np.var(counts, ddof=1) / np.mean(counts) == pytest.approx(1.0, abs=0.12)

    generator = BranchingChainGenerator(model)
    times = generator.sample(
        ConstantRateProfile(model.source_rate_cps),
        0.0,
        20.0,
        np.random.default_rng(987),
    )
    scaled_intervals = np.diff(times) * model.expected_detected_rate_cps
    ordered = np.sort(scaled_intervals)
    sample_size = ordered.size
    theoretical_cdf = 1.0 - np.exp(-ordered)
    empirical_upper = np.arange(1, sample_size + 1, dtype=np.float64) / sample_size
    empirical_lower = np.arange(sample_size, dtype=np.float64) / sample_size
    ks_distance = max(
        float(np.max(empirical_upper - theoretical_cdf)),
        float(np.max(theoretical_cdf - empirical_lower)),
    )
    lag_one = float(np.corrcoef(scaled_intervals[:-1], scaled_intervals[1:])[0, 1])
    assert ks_distance < 0.03
    assert abs(lag_one) < 0.05


def test_count_correlation_strength_increases_with_k_eff() -> None:
    low = prompt_model(0.1, 9_000.0)
    high = prompt_model(0.5, 5_000.0)
    low_counts = np.asarray(
        [sample_count(low, duration_s=0.02, seed=seed) for seed in range(400)],
        dtype=np.float64,
    )
    high_counts = np.asarray(
        [sample_count(high, duration_s=0.02, seed=seed) for seed in range(400)],
        dtype=np.float64,
    )

    low_fano = float(np.var(low_counts, ddof=1) / np.mean(low_counts))
    high_fano = float(np.var(high_counts, ddof=1) / np.mean(high_counts))
    assert low_fano > 1.0
    assert high_fano > low_fano + 0.1


def test_reaction_guard_fails_instead_of_truncating() -> None:
    model = prompt_model(0.2, 8_000.0)
    generator = BranchingChainGenerator(model, max_total_reactions=1)

    with pytest.raises(ValueError, match="max_total_reactions"):
        generator.sample(
            ConstantRateProfile(model.source_rate_cps),
            0.0,
            0.1,
            np.random.default_rng(789),
        )


def test_streaming_windows_must_be_contiguous() -> None:
    model = prompt_model(0.2, 8_000.0)
    profile = ConstantRateProfile(model.source_rate_cps)
    generator = BranchingChainGenerator(model)
    rng = np.random.default_rng(101)
    generator.sample(profile, 0.0, 0.01, rng)

    with pytest.raises(ValueError, match="contiguous"):
        generator.sample(profile, 0.02, 0.01, rng)
