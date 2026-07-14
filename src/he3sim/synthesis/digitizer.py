"""Analog clipping and uniform ADC quantization."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class AnalogClipResult:
    """Clipped analog samples and the samples changed by clipping."""

    samples_V: npt.NDArray[np.float64]
    saturation_mask: npt.NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class DigitizedSamples:
    """Unsigned ADC codes and samples outside the configured ADC input range."""

    adc_samples: npt.NDArray[np.uint16]
    saturation_mask: npt.NDArray[np.bool_]


def _validate_range(low_V: float, high_V: float) -> None:
    """Require a finite ordered voltage range."""
    if not math.isfinite(low_V) or not math.isfinite(high_V) or high_V <= low_V:
        raise ValueError("voltage range must be finite with maximum greater than minimum")


def clip_analog(
    samples_V: npt.ArrayLike,
    minimum_V: float,
    maximum_V: float,
) -> AnalogClipResult:
    """Clip analog voltage and mark only samples outside the closed range."""
    _validate_range(minimum_V, maximum_V)
    samples = np.asarray(samples_V, dtype=np.float64)
    if samples.ndim != 1 or np.any(~np.isfinite(samples)):
        raise ValueError("samples_V must be a finite one-dimensional array")
    saturated = (samples < minimum_V) | (samples > maximum_V)
    return AnalogClipResult(
        samples_V=np.clip(samples, minimum_V, maximum_V),
        saturation_mask=saturated,
    )


def quantize_adc(
    samples_V: npt.ArrayLike,
    bits: int,
    input_min_V: float,
    input_max_V: float,
    offset_V: float = 0.0,
) -> DigitizedSamples:
    """Apply input offset, rail clipping, and nearest-code uniform quantization."""
    if isinstance(bits, bool) or not isinstance(bits, (int, np.integer)) or not 1 <= bits <= 16:
        raise ValueError("bits must be an integer within [1, 16]")
    _validate_range(input_min_V, input_max_V)
    if not math.isfinite(offset_V):
        raise ValueError("offset_V must be finite")
    samples = np.asarray(samples_V, dtype=np.float64)
    if samples.ndim != 1 or np.any(~np.isfinite(samples)):
        raise ValueError("samples_V must be a finite one-dimensional array")

    shifted = samples + offset_V
    saturated = (shifted < input_min_V) | (shifted > input_max_V)
    clipped = np.clip(shifted, input_min_V, input_max_V)
    maximum_code = (1 << int(bits)) - 1
    normalized = (clipped - input_min_V) / (input_max_V - input_min_V)
    adc_samples = np.rint(normalized * maximum_code).astype(np.uint16)
    return DigitizedSamples(adc_samples=adc_samples, saturation_mask=saturated)
