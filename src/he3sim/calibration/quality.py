"""Provisional index-domain QC for Phase 4Q event records."""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

from he3sim.calibration.models import DuplicateMetrics, EventQCResult, QCStatus
from he3sim.calibration.profile import QCThresholdProfile


def duplicate_metrics(
    samples: npt.NDArray[np.int64],
    candidate_pair_fraction: float = 0.95,
) -> DuplicateMetrics:
    """Measure adjacent repetition without changing the sample sequence."""
    if not 0.0 < candidate_pair_fraction <= 1.0:
        raise ValueError("candidate_pair_fraction must be in (0, 1]")
    count = int(samples.size)
    even_left = samples[0 : count - 1 : 2]
    even_right = samples[1:count:2]
    odd_left = samples[1 : count - 1 : 2]
    odd_right = samples[2:count:2]
    even_fraction = float(np.mean(even_left == even_right)) if even_left.size else 0.0
    odd_fraction = float(np.mean(odd_left == odd_right)) if odd_left.size else 0.0
    lag1_fraction = float(np.mean(samples[:-1] == samples[1:])) if count > 1 else 0.0
    candidate_count = (count + 1) // 2 if even_fraction >= candidate_pair_fraction else count
    return DuplicateMetrics(
        exported_sample_count=count,
        candidate_deduplicated_sample_count=candidate_count,
        even_pair_equal_fraction=even_fraction,
        odd_pair_equal_fraction=odd_fraction,
        lag1_equal_fraction=lag1_fraction,
    )


def _status(condition: bool) -> QCStatus:
    return QCStatus.FAIL if condition else QCStatus.PASS


def evaluate_event_qc(
    samples: npt.NDArray[np.int64],
    polarity: int | None,
    thresholds: QCThresholdProfile,
) -> EventQCResult:
    """Evaluate one event while keeping absent evidence explicitly non-evaluable."""
    if samples.ndim != 1 or samples.size < 8:
        raise ValueError("event QC requires at least eight one-dimensional samples")
    values = samples.astype(np.float64, copy=False)
    count = values.size
    baseline_count = max(4, int(math.ceil(count * thresholds.baseline_fraction)))
    tail_count = max(4, int(math.ceil(count * thresholds.tail_fraction)))
    baseline_values = values[:baseline_count]
    baseline = float(np.median(baseline_values))
    mad = float(np.median(np.abs(baseline_values - baseline)))
    noise_sigma = 1.4826 * mad
    if noise_sigma == 0.0:
        noise_sigma = float(np.std(baseline_values))
    half = max(1, baseline_count // 2)
    baseline_shift = float(
        abs(np.median(baseline_values[-half:]) - np.median(baseline_values[:half]))
    )
    duplicate = duplicate_metrics(samples, thresholds.duplicate_pair_fraction)

    statuses: dict[str, QCStatus] = {
        "duplicate_samples": _status(
            duplicate.even_pair_equal_fraction >= thresholds.duplicate_pair_fraction
        ),
        "baseline_unstable": _status(
            baseline_shift > thresholds.baseline_drift_sigma * max(noise_sigma, 1.0)
        ),
    }
    reasons: dict[str, str] = {
        "duplicate_samples": "exact adjacent-pair repetition in exported sample indices",
        "baseline_unstable": "provisional robust pretrigger drift test in ADC counts",
    }
    metrics: dict[str, int | float | None] = {
        "baseline_ADC_counts": baseline,
        "baseline_noise_sigma_ADC_counts": noise_sigma,
        "baseline_shift_ADC_counts": baseline_shift,
        "peak_index_exported": None,
        "peak_amplitude_ADC_counts": None,
        "tail_offset_ADC_counts": None,
        "ringing_alternations": None,
        "sample_interval_s": None,
    }

    if thresholds.adc_min_count is None or thresholds.adc_max_count is None:
        statuses["saturation"] = QCStatus.NOT_EVALUABLE
        reasons["saturation"] = "ADC waveform rails are not independently confirmed"
    else:
        statuses["saturation"] = _status(
            bool(
                np.any(samples <= thresholds.adc_min_count)
                or np.any(samples >= thresholds.adc_max_count)
            )
        )
        reasons["saturation"] = "configured provisional ADC rail contact test"

    if polarity not in {-1, 1}:
        for name in ("tail_truncated", "ringing", "low_amplitude", "trigger_clipped"):
            statuses[name] = QCStatus.NOT_EVALUABLE
            reasons[name] = "channel polarity is not explicitly available"
        return EventQCResult(metrics, statuses, reasons, duplicate)

    aligned = polarity * (values - baseline)
    peak_index = int(np.argmax(aligned))
    peak = float(aligned[peak_index])
    tail_offset = float(abs(np.median(aligned[-tail_count:])))
    metrics["peak_index_exported"] = peak_index
    metrics["peak_amplitude_ADC_counts"] = peak
    metrics["tail_offset_ADC_counts"] = tail_offset

    snr = peak / max(noise_sigma, 1.0)
    statuses["low_amplitude"] = _status(snr < thresholds.low_amplitude_snr)
    reasons["low_amplitude"] = "provisional robust peak-to-baseline-noise ratio"
    statuses["tail_truncated"] = _status(
        peak <= 0.0 or tail_offset > thresholds.tail_return_peak_fraction * peak
    )
    reasons["tail_truncated"] = "tail has not returned near the robust baseline"

    tail = aligned[peak_index + 1 :]
    significant = tail[np.abs(tail) >= thresholds.ringing_peak_fraction * max(peak, 1.0)]
    signs = np.sign(significant)
    alternations = int(np.count_nonzero(signs[1:] != signs[:-1])) if signs.size > 1 else 0
    metrics["ringing_alternations"] = alternations
    statuses["ringing"] = _status(alternations >= thresholds.ringing_min_alternations)
    reasons["ringing"] = "provisional post-peak baseline-crossing alternation count"

    crossing_candidates = np.flatnonzero(aligned >= thresholds.trigger_fraction * max(peak, 1.0))
    first_crossing = int(crossing_candidates[0]) if crossing_candidates.size else 0
    statuses["trigger_clipped"] = _status(
        first_crossing < thresholds.min_pretrigger_exported_samples
    )
    reasons["trigger_clipped"] = "insufficient exported samples before provisional leading edge"
    return EventQCResult(metrics, statuses, reasons, duplicate)
