"""Local-only Web integration for the validated simulation pipeline."""

from he3sim.app.web_backend import (
    MAX_WEB_EXPECTED_EVENTS,
    MAX_WEB_WAVEFORM_SAMPLES,
    InteractiveDurationLimit,
    InteractiveRunResult,
    InteractiveWaveformRequest,
    WaveformResourceEstimate,
    estimate_waveform_resources,
    generate_interactive_waveform,
    maximum_interactive_duration,
    write_waveform_csv,
)

__all__ = [
    "MAX_WEB_EXPECTED_EVENTS",
    "MAX_WEB_WAVEFORM_SAMPLES",
    "InteractiveRunResult",
    "InteractiveWaveformRequest",
    "InteractiveDurationLimit",
    "WaveformResourceEstimate",
    "estimate_waveform_resources",
    "generate_interactive_waveform",
    "maximum_interactive_duration",
    "write_waveform_csv",
]
