from __future__ import annotations

import numpy as np

from he3sim.synthesis.digitizer import clip_analog, quantize_adc
from he3sim.synthesis.noise import AR1DriftGenerator, gaussian_white_noise


def test_analog_clipping_and_adc_mapping_mark_saturation() -> None:
    samples = np.array([-2.0, -1.0, 0.0, 1.0, 2.0], dtype=np.float64)
    clipped = clip_analog(samples, -1.5, 1.5)
    np.testing.assert_array_equal(clipped.samples_V, [-1.5, -1.0, 0.0, 1.0, 1.5])
    np.testing.assert_array_equal(clipped.saturation_mask, [True, False, False, False, True])

    digitized = quantize_adc(samples, bits=3, input_min_V=-1.0, input_max_V=1.0)
    np.testing.assert_array_equal(digitized.adc_samples, [0, 0, 4, 7, 7])
    np.testing.assert_array_equal(
        digitized.saturation_mask,
        [True, False, False, False, True],
    )
    assert digitized.adc_samples.dtype == np.uint16


def test_adc_offset_is_applied_before_quantization() -> None:
    without_offset = quantize_adc([0.0], 8, -1.0, 1.0)
    with_offset = quantize_adc([0.0], 8, -1.0, 1.0, offset_V=0.5)

    assert int(with_offset.adc_samples[0]) > int(without_offset.adc_samples[0])


def test_white_noise_is_reproducible_for_a_fixed_seed() -> None:
    left = gaussian_white_noise(2_000, 0.01, np.random.default_rng(1234))
    right = gaussian_white_noise(2_000, 0.01, np.random.default_rng(1234))
    different = gaussian_white_noise(2_000, 0.01, np.random.default_rng(1235))

    np.testing.assert_array_equal(left, right)
    assert not np.array_equal(left, different)


def test_ar1_drift_preserves_state_and_random_sequence_across_blocks() -> None:
    full_generator = AR1DriftGenerator(0.01, 1.0e-4, 100.0e6)
    blocked_generator = AR1DriftGenerator(0.01, 1.0e-4, 100.0e6)
    full = full_generator.sample(100, np.random.default_rng(42))
    blocked_rng = np.random.default_rng(42)
    blocked = np.concatenate(
        [
            blocked_generator.sample(37, blocked_rng),
            blocked_generator.sample(63, blocked_rng),
        ]
    )

    np.testing.assert_array_equal(blocked, full)
