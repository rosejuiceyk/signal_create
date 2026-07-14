"""Traceable many-to-many links between waveform triggers and truth events."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from he3sim.types import TRIGGER_EVENT_LINK_DTYPE, TRUE_EVENT_DTYPE


def match_triggers_to_truth(
    trigger_times_s: npt.ArrayLike,
    true_events: npt.NDArray[np.void],
    pre_trigger_s: float,
    post_trigger_s: float,
) -> npt.NDArray[np.void]:
    """Link every trigger to all truth events inside its stored event window."""
    triggers = np.asarray(trigger_times_s, dtype=np.float64)
    if triggers.ndim != 1 or np.any(~np.isfinite(triggers)):
        raise ValueError("trigger times must be finite and one-dimensional")
    if true_events.ndim != 1 or true_events.dtype != TRUE_EVENT_DTYPE:
        raise ValueError("true_events must use TRUE_EVENT_DTYPE")
    if pre_trigger_s < 0.0 or post_trigger_s <= 0.0:
        raise ValueError("association window requires non-negative pre and positive post")
    event_times = true_events["t_s"]
    rows: list[tuple[int, int, float]] = []
    for trigger_id, trigger_s in enumerate(triggers):
        start = int(np.searchsorted(event_times, trigger_s - pre_trigger_s, side="left"))
        stop = int(np.searchsorted(event_times, trigger_s + post_trigger_s, side="right"))
        for event in true_events[start:stop]:
            rows.append((trigger_id, int(event["event_id"]), float(event["t_s"] - trigger_s)))
    return np.asarray(rows, dtype=TRIGGER_EVENT_LINK_DTYPE)
