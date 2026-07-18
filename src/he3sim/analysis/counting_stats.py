"""Deterministic statistical diagnostics for Phase 1 arrival generators."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from he3sim.physics.arrivals import ArrivalAlgorithm, arrival_generator_for
from he3sim.physics.rate_profiles import ConstantRateProfile

MIN_EXPECTED_EVENTS_PER_REPLICATE = 100.0
FANO_SIGMA_MULTIPLIER = 3.0
MEAN_SIGMA_MULTIPLIER = 5.0
MIN_MEAN_RELATIVE_TOLERANCE = 0.02
MIN_INTERVAL_MEAN_RELATIVE_TOLERANCE = 0.02
KS_DISTANCE_MULTIPLIER = 4.0
MIN_KS_DISTANCE_TOLERANCE = 0.01


@dataclass(frozen=True, slots=True)
class AlgorithmStatistics:
    """Count and interval diagnostics for one arrival algorithm."""

    count_mean: float
    count_variance: float
    fano_factor: float
    mean_relative_error: float
    interval_sample_size: int
    interval_mean_s: float
    theoretical_interval_mean_s: float
    interval_mean_relative_error: float
    exponential_ks_distance: float
    exponential_ks_distance_tolerance: float
    passed: bool


@dataclass(frozen=True, slots=True)
class ArrivalValidationReport:
    """Complete deterministic comparison of both Phase 1 arrival algorithms."""

    true_rate_cps: float
    validation_duration_s: float
    expected_count: float
    replicates: int
    seed: int
    mean_relative_tolerance: float
    fano_absolute_tolerance: float
    interval_mean_relative_tolerance: float
    interval_two_sample_ks_tolerance: float
    algorithms: dict[str, AlgorithmStatistics]
    count_mean_relative_difference: float
    fano_absolute_difference: float
    interval_two_sample_ks_distance: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible report mapping."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ArrivalValidationArtifacts:
    """Report plus bounded samples needed to render diagnostic figures."""

    report: ArrivalValidationReport
    counts: dict[str, npt.NDArray[np.int64]]
    scaled_intervals: dict[str, npt.NDArray[np.float64]]


def exponential_ks_distance(scaled_intervals: npt.NDArray[np.float64]) -> float:
    """Return the one-sample KS distance to an Exp(1) CDF without a p-value."""
    values = np.sort(np.asarray(scaled_intervals, dtype=np.float64))
    if values.size == 0:
        return float("inf")
    expected_cdf = -np.expm1(-values)
    indices = np.arange(1, values.size + 1, dtype=np.float64)
    upper = np.max(indices / values.size - expected_cdf)
    lower = np.max(expected_cdf - (indices - 1.0) / values.size)
    return float(max(upper, lower))


def two_sample_ks_distance(
    left: npt.NDArray[np.float64],
    right: npt.NDArray[np.float64],
) -> float:
    """Return the two-sample empirical-CDF distance without a p-value."""
    left_sorted = np.sort(np.asarray(left, dtype=np.float64))
    right_sorted = np.sort(np.asarray(right, dtype=np.float64))
    if left_sorted.size == 0 or right_sorted.size == 0:
        return float("inf")
    combined = np.concatenate((left_sorted, right_sorted))
    left_cdf = np.searchsorted(left_sorted, combined, side="right") / left_sorted.size
    right_cdf = np.searchsorted(right_sorted, combined, side="right") / right_sorted.size
    return float(np.max(np.abs(left_cdf - right_cdf)))


def validate_arrival_algorithms(
    true_rate_cps: float,
    configured_duration_s: float,
    seed: int,
    replicates: int = 500,
) -> ArrivalValidationArtifacts:
    """Run fixed-seed count, Fano, interval, and cross-algorithm diagnostics."""
    if not np.isfinite(true_rate_cps) or true_rate_cps <= 0.0:
        raise ValueError("true_rate_cps must be finite and positive")
    if not np.isfinite(configured_duration_s) or configured_duration_s <= 0.0:
        raise ValueError("configured_duration_s must be finite and positive")
    if replicates < 30:
        raise ValueError("replicates must be at least 30 for stable diagnostics")

    validation_duration_s = max(
        configured_duration_s,
        MIN_EXPECTED_EVENTS_PER_REPLICATE / true_rate_cps,
    )
    expected_count = true_rate_cps * validation_duration_s
    root_sequence = np.random.SeedSequence(seed)
    child_sequences = root_sequence.spawn(len(ArrivalAlgorithm))
    profile = ConstantRateProfile(true_rate_cps)

    counts_by_algorithm: dict[str, npt.NDArray[np.int64]] = {}
    intervals_by_algorithm: dict[str, npt.NDArray[np.float64]] = {}
    statistics: dict[str, AlgorithmStatistics] = {}

    mean_tolerance = float(
        max(
            MIN_MEAN_RELATIVE_TOLERANCE,
            MEAN_SIGMA_MULTIPLIER / np.sqrt(replicates * expected_count),
        )
    )
    fano_tolerance = float(
        max(
            0.15,
            FANO_SIGMA_MULTIPLIER * np.sqrt(2.0 / (replicates - 1)),
        )
    )

    for raw_algorithm, child_sequence in zip(ArrivalAlgorithm, child_sequences, strict=True):
        algorithm = ArrivalAlgorithm(raw_algorithm)
        generator = arrival_generator_for(algorithm)
        rng = np.random.default_rng(child_sequence)
        counts = np.empty(replicates, dtype=np.int64)
        interval_chunks: list[npt.NDArray[np.float64]] = []
        for replicate in range(replicates):
            times_s = generator.sample(profile, 0.0, validation_duration_s, rng)
            counts[replicate] = times_s.size
            if times_s.size:
                intervals_s = np.diff(np.concatenate((np.array([0.0]), times_s)))
                interval_chunks.append(intervals_s)

        intervals_s = (
            np.concatenate(interval_chunks) if interval_chunks else np.empty(0, dtype=np.float64)
        )
        scaled_intervals = intervals_s * true_rate_cps
        count_mean = float(np.mean(counts))
        count_variance = float(np.var(counts, ddof=1))
        fano_factor = count_variance / count_mean if count_mean > 0.0 else float("inf")
        mean_relative_error = abs(count_mean - expected_count) / expected_count
        interval_mean_s = float(np.mean(intervals_s)) if intervals_s.size else float("inf")
        theoretical_interval_mean_s = 1.0 / true_rate_cps
        interval_mean_relative_error = (
            abs(interval_mean_s - theoretical_interval_mean_s) / theoretical_interval_mean_s
        )
        interval_mean_tolerance = float(
            max(
                MIN_INTERVAL_MEAN_RELATIVE_TOLERANCE,
                MEAN_SIGMA_MULTIPLIER / np.sqrt(max(1, intervals_s.size)),
            )
        )
        ks_distance = exponential_ks_distance(scaled_intervals)
        ks_tolerance = float(
            max(
                MIN_KS_DISTANCE_TOLERANCE,
                KS_DISTANCE_MULTIPLIER / np.sqrt(max(1, intervals_s.size)),
            )
        )
        algorithm_passed = bool(
            mean_relative_error <= mean_tolerance
            and abs(fano_factor - 1.0) <= fano_tolerance
            and interval_mean_relative_error <= interval_mean_tolerance
            and ks_distance <= ks_tolerance
        )
        counts_by_algorithm[algorithm.value] = counts
        intervals_by_algorithm[algorithm.value] = scaled_intervals
        statistics[algorithm.value] = AlgorithmStatistics(
            count_mean=count_mean,
            count_variance=count_variance,
            fano_factor=fano_factor,
            mean_relative_error=mean_relative_error,
            interval_sample_size=int(intervals_s.size),
            interval_mean_s=interval_mean_s,
            theoretical_interval_mean_s=theoretical_interval_mean_s,
            interval_mean_relative_error=interval_mean_relative_error,
            exponential_ks_distance=ks_distance,
            exponential_ks_distance_tolerance=ks_tolerance,
            passed=algorithm_passed,
        )

    uniform_stats = statistics[ArrivalAlgorithm.POISSON_UNIFORM.value]
    exponential_stats = statistics[ArrivalAlgorithm.CUMULATIVE_EXPONENTIAL.value]
    count_mean_relative_difference = (
        abs(uniform_stats.count_mean - exponential_stats.count_mean) / expected_count
    )
    fano_absolute_difference = abs(uniform_stats.fano_factor - exponential_stats.fano_factor)
    interval_two_sample_distance = two_sample_ks_distance(
        intervals_by_algorithm[ArrivalAlgorithm.POISSON_UNIFORM.value],
        intervals_by_algorithm[ArrivalAlgorithm.CUMULATIVE_EXPONENTIAL.value],
    )
    left_interval_count = intervals_by_algorithm[ArrivalAlgorithm.POISSON_UNIFORM.value].size
    right_interval_count = intervals_by_algorithm[
        ArrivalAlgorithm.CUMULATIVE_EXPONENTIAL.value
    ].size
    effective_interval_count = (
        left_interval_count * right_interval_count / (left_interval_count + right_interval_count)
    )
    interval_two_sample_tolerance = float(
        max(
            MIN_KS_DISTANCE_TOLERANCE,
            KS_DISTANCE_MULTIPLIER / np.sqrt(effective_interval_count),
        )
    )
    fano_difference_tolerance = float(
        max(
            0.20,
            FANO_SIGMA_MULTIPLIER * np.sqrt(4.0 / (replicates - 1)),
        )
    )
    comparison_passed = bool(
        count_mean_relative_difference <= 0.04
        and fano_absolute_difference <= fano_difference_tolerance
        and interval_two_sample_distance <= interval_two_sample_tolerance
    )
    passed = bool(all(item.passed for item in statistics.values()) and comparison_passed)
    report = ArrivalValidationReport(
        true_rate_cps=true_rate_cps,
        validation_duration_s=validation_duration_s,
        expected_count=expected_count,
        replicates=replicates,
        seed=seed,
        mean_relative_tolerance=mean_tolerance,
        fano_absolute_tolerance=fano_tolerance,
        interval_mean_relative_tolerance=float(
            max(
                MIN_INTERVAL_MEAN_RELATIVE_TOLERANCE,
                MEAN_SIGMA_MULTIPLIER
                / np.sqrt(min(item.interval_sample_size for item in statistics.values())),
            )
        ),
        interval_two_sample_ks_tolerance=interval_two_sample_tolerance,
        algorithms=statistics,
        count_mean_relative_difference=count_mean_relative_difference,
        fano_absolute_difference=fano_absolute_difference,
        interval_two_sample_ks_distance=interval_two_sample_distance,
        passed=passed,
    )
    return ArrivalValidationArtifacts(
        report=report,
        counts=counts_by_algorithm,
        scaled_intervals=intervals_by_algorithm,
    )
