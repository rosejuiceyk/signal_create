from __future__ import annotations

import numpy as np
import pytest

from he3sim.synthesis.renderers import (
    RecursiveFixedTauRenderer,
    render_direct_sparse,
    render_recursive_fixed_tau,
)
from he3sim.types import TRUE_EVENT_DTYPE

SAMPLE_RATE_HZ = 100.0e6
TAU_R_S = 20.0e-9
TAU_D_S = 200.0e-9


def make_events(times_s: list[float], polarities: list[int] | None = None) -> np.ndarray:
    events = np.zeros(len(times_s), dtype=TRUE_EVENT_DTYPE)
    events["event_id"] = np.arange(len(times_s))
    events["t_s"] = times_s
    events["energy_dep_keV"] = 764.0
    events["amplitude_peak_V"] = np.linspace(0.1, 0.2, len(times_s))
    events["tau_r_s"] = TAU_R_S
    events["tau_d_s"] = TAU_D_S
    events["polarity"] = polarities or [1] * len(times_s)
    events["parameter_status"] = b"synthetic_demo"
    return events


def test_time_translation_and_two_event_linear_superposition() -> None:
    shift_samples = 7
    left = make_events([20.0 / SAMPLE_RATE_HZ])
    right = make_events([(20.0 + shift_samples) / SAMPLE_RATE_HZ])
    left_waveform = render_direct_sparse(left, 300, SAMPLE_RATE_HZ)
    right_waveform = render_direct_sparse(right, 300, SAMPLE_RATE_HZ)
    np.testing.assert_allclose(
        right_waveform[shift_samples:],
        left_waveform[:-shift_samples],
        rtol=1.0e-13,
        atol=1.0e-15,
    )

    first = make_events([20.25 / SAMPLE_RATE_HZ])
    second = make_events([28.75 / SAMPLE_RATE_HZ], [-1])
    combined = np.concatenate([first, second])
    combined["event_id"] = np.arange(2)
    rendered_sum = render_direct_sparse(combined, 300, SAMPLE_RATE_HZ)
    expected = render_direct_sparse(first, 300, SAMPLE_RATE_HZ) + render_direct_sparse(
        second, 300, SAMPLE_RATE_HZ
    )
    np.testing.assert_allclose(rendered_sum, expected, rtol=1.0e-13, atol=1.0e-15)


def test_recursive_fixed_tau_matches_direct_reference_for_pileup_and_polarity() -> None:
    events = make_events(
        [20.25e-9, 72.75e-9, 75.0e-9, 900.5e-9],
        [1, -1, 1, -1],
    )
    sample_count = 500

    direct = render_direct_sparse(events, sample_count, SAMPLE_RATE_HZ)
    recursive = render_recursive_fixed_tau(events, sample_count, SAMPLE_RATE_HZ)

    np.testing.assert_allclose(recursive, direct, rtol=2.0e-12, atol=2.0e-14)


def test_recursive_partitioned_and_whole_rendering_are_identical_across_boundaries() -> None:
    events = make_events(
        [15.25 / SAMPLE_RATE_HZ, 63.75 / SAMPLE_RATE_HZ, 64.0 / SAMPLE_RATE_HZ],
        [1, 1, -1],
    )
    renderer = RecursiveFixedTauRenderer.from_events(events, SAMPLE_RATE_HZ)
    state = None
    blocks = []
    injected = 0
    for start, length in ((0, 64), (64, 31), (95, 105)):
        block, state, count = renderer.render_block(events, start, length, state)
        blocks.append(block)
        injected += count

    whole = render_recursive_fixed_tau(events, 200, SAMPLE_RATE_HZ)
    np.testing.assert_array_equal(np.concatenate(blocks), whole)
    assert injected == events.size


def test_recursive_backend_rejects_variable_time_constants_but_reference_supports_them() -> None:
    events = make_events([20.0e-9, 80.0e-9])
    events["tau_d_s"][1] = 300.0e-9

    direct = render_direct_sparse(events, 200, SAMPLE_RATE_HZ)

    assert np.any(direct != 0.0)
    with pytest.raises(ValueError, match="shared tau_d_s"):
        render_recursive_fixed_tau(events, 200, SAMPLE_RATE_HZ)
