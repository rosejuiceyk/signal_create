"""Static, read-only visualization of Phase 2 waveform HDF5 files."""

from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "he3sim-matplotlib"),
)
import h5py  # type: ignore[import-untyped]  # noqa: E402
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import numpy.typing as npt  # noqa: E402

DEFAULT_MAX_OVERVIEW_POINTS = 4_000
MAX_FOCUS_SAMPLES = 50_000
MAX_DETAIL_EVENT_MARKERS = 80
MAX_SATURATION_MARKERS = 500
BLUE = "#2F6B9A"
BLUE_LIGHT = "#C8DCEB"
GOLD = "#C28B2C"
ORANGE = "#D4652F"
INK = "#263238"
GRID = "#D9DEE3"


@dataclass(frozen=True, slots=True)
class WaveformPlotSummary:
    """Metadata describing one exported waveform review figure."""

    output_path: Path
    sample_count: int
    event_count: int
    selected_event_id: int | None
    parameter_status: str
    focus_saturation_fraction: float
    nearby_event_count: int
    plotted_event_marker_count: int


def _attribute(group: h5py.Group, name: str, default: Any = None) -> Any:
    """Return one normalized scalar HDF5 attribute."""
    value = group.attrs.get(name, default)
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.generic):
        return value.item()
    return value


def _time_axis_scale(duration_s: float) -> tuple[float, str]:
    """Choose a readable absolute-time unit for the overview panel."""
    if duration_s < 1.0e-3:
        return 1.0e6, "µs"
    if duration_s < 1.0:
        return 1.0e3, "ms"
    return 1.0, "s"


def _min_max_envelope(
    dataset: h5py.Dataset,
    max_points: int,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Read a bounded min/max envelope without loading a large dataset at once."""
    sample_count = int(dataset.shape[0])
    if sample_count <= 0:
        raise ValueError("waveform dataset must contain at least one sample")
    if max_points < 100:
        raise ValueError("max_overview_points must be at least 100")
    bin_count = min(sample_count, max_points)
    bin_width = math.ceil(sample_count / bin_count)
    centers: list[float] = []
    minima: list[float] = []
    maxima: list[float] = []
    bins_per_read = 256
    total_bins = math.ceil(sample_count / bin_width)
    for first_bin in range(0, total_bins, bins_per_read):
        first_sample = first_bin * bin_width
        stop_sample = min(sample_count, (first_bin + bins_per_read) * bin_width)
        values = np.asarray(dataset[first_sample:stop_sample], dtype=np.float64)
        for local_start in range(0, values.size, bin_width):
            segment = values[local_start : local_start + bin_width]
            global_start = first_sample + local_start
            global_stop = global_start + segment.size
            centers.append(0.5 * (global_start + global_stop - 1))
            minima.append(float(np.min(segment)))
            maxima.append(float(np.max(segment)))
    return (
        np.asarray(centers, dtype=np.float64),
        np.asarray(minima, dtype=np.float64),
        np.asarray(maxima, dtype=np.float64),
    )


def _select_event_index(events: h5py.Dataset, event_id: int | None) -> int | None:
    """Select an explicit event or the largest target-amplitude event."""
    event_count = int(events.shape[0])
    if event_count == 0:
        if event_id is not None:
            raise ValueError("cannot select an event from an empty truth-event table")
        return None
    if event_id is None:
        amplitudes = np.asarray(events["amplitude_peak_V"], dtype=np.float64)
        return int(np.argmax(amplitudes))
    event_ids = np.asarray(events["event_id"], dtype=np.int64)
    matches = np.flatnonzero(event_ids == event_id)
    if matches.size != 1:
        raise ValueError(f"event_id {event_id} is not present exactly once")
    return int(matches[0])


def _focus_bounds(
    selected_event: np.void | None,
    sample_count: int,
    sample_rate_hz: float,
) -> tuple[int, int, int]:
    """Choose a bounded review window around one event or the run midpoint."""
    if selected_event is None:
        center = sample_count // 2
        half_width = min(MAX_FOCUS_SAMPLES // 2, max(100, sample_count // 20))
        return max(0, center - half_width), min(sample_count, center + half_width), center
    center = int(selected_event["sample_index"])
    tau_r_s = float(selected_event["tau_r_s"])
    tau_d_s = float(selected_event["tau_d_s"])
    pre_samples = max(50, math.ceil(3.0 * tau_r_s * sample_rate_hz))
    post_samples = max(200, math.ceil(8.0 * tau_d_s * sample_rate_hz))
    total = pre_samples + post_samples + 1
    if total > MAX_FOCUS_SAMPLES:
        scale = MAX_FOCUS_SAMPLES / total
        pre_samples = max(1, int(pre_samples * scale))
        post_samples = MAX_FOCUS_SAMPLES - pre_samples - 1
    return max(0, center - pre_samples), min(sample_count, center + post_samples + 1), center


def _adaptive_y_limits(
    values: npt.NDArray[np.float64],
    *,
    minimum_padding: float,
) -> tuple[float, float]:
    """Return finite data-driven limits with visible padding for constant signals."""
    finite = np.asarray(values, dtype=np.float64).ravel()
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        raise ValueError("cannot determine y-axis limits without finite samples")
    if not math.isfinite(minimum_padding) or minimum_padding <= 0.0:
        raise ValueError("minimum_padding must be finite and positive")
    minimum = float(np.min(finite))
    maximum = float(np.max(finite))
    span = maximum - minimum
    if span > 0.0:
        padding = max(minimum_padding, 0.08 * span)
    else:
        scale = max(abs(minimum), minimum_padding * 10.0)
        padding = max(minimum_padding, 0.02 * scale)
    return minimum - padding, maximum + padding


def _bounded_marker_samples(
    sample_indices: npt.NDArray[np.int64],
    *,
    selected_sample: int | None,
    maximum: int = MAX_DETAIL_EVENT_MARKERS,
) -> npt.NDArray[np.int64]:
    """Select representative event markers without obscuring a dense waveform."""
    if maximum <= 0:
        raise ValueError("maximum marker count must be positive")
    samples = np.unique(np.asarray(sample_indices, dtype=np.int64))
    if samples.size <= maximum:
        return samples
    selected_positions = np.linspace(0, samples.size - 1, maximum, dtype=np.int64)
    if selected_sample is not None:
        matches = np.flatnonzero(samples == selected_sample)
        if matches.size and not np.any(selected_positions == matches[0]):
            selected_positions[maximum // 2] = matches[0]
    return samples[np.unique(np.sort(selected_positions))]


def _bounded_true_indices(mask: npt.NDArray[np.bool_], maximum: int) -> npt.NDArray[np.int64]:
    """Return at most ``maximum`` representative true positions from a mask."""
    positions = np.flatnonzero(mask).astype(np.int64, copy=False)
    if positions.size <= maximum:
        return positions
    selected = np.linspace(0, positions.size - 1, maximum, dtype=np.int64)
    return positions[selected]


def plot_waveform_hdf5(
    input_path: str | Path,
    output_path: str | Path,
    event_id: int | None = None,
    max_overview_points: int = DEFAULT_MAX_OVERVIEW_POINTS,
) -> WaveformPlotSummary:
    """Export a three-panel waveform review image without modifying the source HDF5."""
    source = Path(input_path)
    destination = Path(output_path)
    if destination.suffix.lower() != ".png":
        raise ValueError("waveform plot output must use the .png extension")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".png.tmp")

    try:
        with h5py.File(source, "r") as handle:
            if "metadata" not in handle or "events/true" not in handle or "blocks" not in handle:
                raise ValueError("input is not a Phase 2 waveform HDF5 file")
            blocks = handle["blocks"]
            preclip_analog = blocks.get("preclip_analog_samples")
            analog = blocks.get("analog_samples")
            adc = blocks.get("adc_samples")
            saturation = blocks.get("saturation_mask")
            if analog is None and adc is None:
                raise ValueError("waveform HDF5 contains neither analog nor ADC samples")
            if preclip_analog is not None:
                overview_dataset = preclip_analog
            elif analog is not None:
                overview_dataset = analog
            else:
                overview_dataset = adc
            if overview_dataset.ndim != 1:
                raise ValueError("waveform sample datasets must be one-dimensional")
            sample_count = int(overview_dataset.shape[0])
            for name, dataset in (
                ("preclip_analog_samples", preclip_analog),
                ("analog_samples", analog),
                ("adc_samples", adc),
                ("saturation_mask", saturation),
            ):
                if dataset is not None and dataset.shape != (sample_count,):
                    raise ValueError(f"{name} does not match the waveform sample count")
            metadata = handle["metadata"]
            sample_rate_hz = float(_attribute(metadata, "sample_rate_hz"))
            if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
                raise ValueError("waveform metadata has an invalid sample_rate_hz")
            events = handle["events/true"]
            event_count = int(events.shape[0])
            selected_index = _select_event_index(events, event_id)
            selected_event = events[selected_index] if selected_index is not None else None
            focus_start, focus_stop, focus_center = _focus_bounds(
                selected_event,
                sample_count,
                sample_rate_hz,
            )

            envelope_x, envelope_min, envelope_max = _min_max_envelope(
                overview_dataset,
                max_overview_points,
            )
            focus_indices = np.arange(focus_start, focus_stop, dtype=np.int64)
            relative_time_us = (focus_indices - focus_center) * (1.0e6 / sample_rate_hz)
            preclip_analog_focus = (
                np.asarray(preclip_analog[focus_start:focus_stop], dtype=np.float64)
                if preclip_analog is not None
                else None
            )
            analog_focus = (
                np.asarray(analog[focus_start:focus_stop], dtype=np.float64)
                if analog is not None
                else None
            )
            adc_focus = (
                np.asarray(adc[focus_start:focus_stop], dtype=np.float64)
                if adc is not None
                else None
            )
            saturation_focus = (
                np.asarray(saturation[focus_start:focus_stop], dtype=np.bool_)
                if saturation is not None
                else np.zeros(focus_stop - focus_start, dtype=np.bool_)
            )
            event_sample_indices = np.asarray(events["sample_index"], dtype=np.int64)
            if np.any(event_sample_indices < 0) or np.any(event_sample_indices >= sample_count):
                raise ValueError("truth-event sample indices lie outside the waveform")
            if np.any(np.diff(event_sample_indices) < 0):
                raise ValueError("truth-event sample indices are not ordered")
            nearby_start = int(np.searchsorted(event_sample_indices, focus_start, side="left"))
            nearby_stop = int(np.searchsorted(event_sample_indices, focus_stop, side="left"))
            nearby_samples = event_sample_indices[nearby_start:nearby_stop]
            selected_sample = (
                int(selected_event["sample_index"]) if selected_event is not None else None
            )
            plotted_marker_samples = _bounded_marker_samples(
                nearby_samples,
                selected_sample=selected_sample,
            )
            focus_saturation_fraction = float(np.mean(saturation_focus))

            duration_s = (sample_count - 1) / sample_rate_hz
            overview_scale, overview_unit = _time_axis_scale(duration_s)
            overview_time = envelope_x * (overview_scale / sample_rate_hz)
            if preclip_analog is not None:
                overview_name = "Pre-clipping analog voltage"
                overview_unit_name = "V"
            elif analog is not None:
                overview_name = "Clipped analog voltage"
                overview_unit_name = "V"
            else:
                overview_name = "ADC code"
                overview_unit_name = "code"
            true_rate_cps = float(_attribute(metadata, "true_rate_cps", float("nan")))
            renderer = str(_attribute(metadata, "renderer", "unknown"))
            seed = int(_attribute(metadata, "seed", -1))
            parameter_status = str(_attribute(metadata, "parameter_status", "unknown"))
            config_hash = str(_attribute(metadata, "config_hash", "unknown"))

            figure, axes = plt.subplots(3, 1, figsize=(13, 9), facecolor="white")
            figure.suptitle("Phase 2 simulated waveform", fontsize=17, color=INK, y=0.975)
            figure.text(
                0.5,
                0.94,
                f"rate={true_rate_cps:g} cps  |  fs={sample_rate_hz / 1.0e6:g} MS/s  |  "
                f"samples={sample_count:,}  |  events={event_count:,}  |  "
                f"renderer={renderer}  |  seed={seed}",
                ha="center",
                va="center",
                fontsize=10,
                color="#54606A",
            )

            overview_axis = axes[0]
            overview_axis.fill_between(
                overview_time,
                envelope_min,
                envelope_max,
                color=BLUE_LIGHT,
                alpha=0.9,
                linewidth=0.0,
                label="min/max envelope",
            )
            overview_axis.plot(overview_time, envelope_max, color=BLUE, linewidth=0.7)
            overview_axis.plot(overview_time, envelope_min, color=BLUE, linewidth=0.7)
            overview_axis.set_title(f"Full-run {overview_name.lower()} overview", loc="left")
            overview_axis.set_xlabel(f"Time ({overview_unit})")
            overview_axis.set_ylabel(f"{overview_name} ({overview_unit_name})")
            overview_axis.set_ylim(
                _adaptive_y_limits(
                    np.concatenate((envelope_min, envelope_max)),
                    minimum_padding=(
                        1.0e-3 if preclip_analog is not None or analog is not None else 1.0
                    ),
                )
            )
            overview_axis.legend(loc="upper right", frameon=False)

            analog_axis = axes[1]
            display_analog_focus = (
                preclip_analog_focus if preclip_analog_focus is not None else analog_focus
            )
            if display_analog_focus is not None:
                analog_axis.plot(
                    relative_time_us,
                    display_analog_focus,
                    color=BLUE,
                    linewidth=1.1,
                )
                analog_axis.set_ylabel(
                    "Pre-clipping voltage (V)"
                    if preclip_analog_focus is not None
                    else "Clipped analog voltage (V)"
                )
                analog_axis.set_ylim(
                    _adaptive_y_limits(display_analog_focus, minimum_padding=1.0e-3)
                )
            else:
                analog_axis.text(
                    0.5,
                    0.5,
                    "Analog samples were not stored",
                    transform=analog_axis.transAxes,
                    ha="center",
                    va="center",
                    color="#66717A",
                )
                analog_axis.set_ylabel("Analog voltage")
            analog_axis.set_title(
                (
                    "Event-centered pre-clipping analog detail"
                    if preclip_analog_focus is not None
                    else "Event-centered clipped analog detail"
                ),
                loc="left",
            )
            analog_axis.set_xlabel("Time relative to selected event (µs)")

            adc_axis = axes[2]
            if adc_focus is not None:
                adc_axis.step(relative_time_us, adc_focus, where="mid", color=GOLD, linewidth=1.0)
                adc_axis.set_ylabel("ADC code")
                if np.any(saturation_focus):
                    saturation_indices = _bounded_true_indices(
                        saturation_focus,
                        MAX_SATURATION_MARKERS,
                    )
                    adc_axis.scatter(
                        relative_time_us[saturation_indices],
                        adc_focus[saturation_indices],
                        color=ORANGE,
                        marker="x",
                        s=18,
                        alpha=0.65,
                        label=f"saturated samples ({focus_saturation_fraction:.1%})",
                        zorder=3,
                    )
                    adc_axis.legend(loc="upper right", frameon=False)
                adc_axis.set_ylim(_adaptive_y_limits(adc_focus, minimum_padding=1.0))
            else:
                adc_axis.text(
                    0.5,
                    0.5,
                    "ADC samples were not stored",
                    transform=adc_axis.transAxes,
                    ha="center",
                    va="center",
                    color="#66717A",
                )
                adc_axis.set_ylabel("ADC code")
            adc_axis.set_title("Event-centered digitized detail", loc="left")
            adc_axis.set_xlabel("Time relative to selected event (µs)")

            for nearby_sample in plotted_marker_samples:
                event_x_us = (nearby_sample - focus_center) * (1.0e6 / sample_rate_hz)
                analog_axis.axvline(
                    event_x_us,
                    color=INK,
                    linestyle="--",
                    linewidth=0.55,
                    alpha=0.25,
                )
                adc_axis.axvline(
                    event_x_us,
                    color=INK,
                    linestyle="--",
                    linewidth=0.55,
                    alpha=0.25,
                )
            if selected_event is not None:
                polarity = int(selected_event["polarity"])
                selected_event_id = int(selected_event["event_id"])
                detail = (
                    f"selected event {selected_event_id}: "
                    f"t={float(selected_event['t_s']) * 1.0e6:.3f} µs, "
                    f"E={float(selected_event['energy_dep_keV']):.3f} keV, "
                    f"A_peak={float(selected_event['amplitude_peak_V']):.6g} V, "
                    f"polarity={polarity:+d}"
                )
                analog_axis.axvline(0.0, color=ORANGE, linewidth=1.1, alpha=0.9)
                adc_axis.axvline(0.0, color=ORANGE, linewidth=1.1, alpha=0.9)
            else:
                selected_event_id = None
                detail = (
                    "No truth event was generated; detail window is centered on the run midpoint."
                )
            analog_axis.text(
                0.01,
                0.95,
                detail,
                transform=analog_axis.transAxes,
                ha="left",
                va="top",
                fontsize=9,
                color=INK,
                bbox={"facecolor": "white", "edgecolor": GRID, "alpha": 0.88},
            )
            analog_axis.text(
                0.99,
                0.04,
                f"nearby events={nearby_samples.size:,}; "
                f"markers shown={plotted_marker_samples.size:,}; "
                f"clipped/ADC saturated samples={focus_saturation_fraction:.1%}",
                transform=analog_axis.transAxes,
                ha="right",
                va="bottom",
                fontsize=8.5,
                color="#5D6871",
                bbox={"facecolor": "white", "edgecolor": GRID, "alpha": 0.82},
            )

            for axis in axes:
                axis.grid(True, color=GRID, linewidth=0.7, alpha=0.7)
                axis.spines[["top", "right"]].set_visible(False)
                axis.tick_params(colors=INK)
            figure.text(
                0.01,
                0.018,
                f"parameter_status={parameter_status}; config_hash={config_hash[:16]}…; "
                "pre-clipping voltage is diagnostic; clipped voltage drives the ADC.",
                ha="left",
                va="bottom",
                fontsize=9,
                color="#5D6871",
            )
            figure.subplots_adjust(top=0.89, bottom=0.09, hspace=0.43)
            figure.savefig(temporary, dpi=160, format="png", facecolor="white")
            plt.close(figure)
        temporary.replace(destination)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return WaveformPlotSummary(
        output_path=destination,
        sample_count=sample_count,
        event_count=event_count,
        selected_event_id=selected_event_id,
        parameter_status=parameter_status,
        focus_saturation_fraction=focus_saturation_fraction,
        nearby_event_count=int(nearby_samples.size),
        plotted_event_marker_count=int(plotted_marker_samples.size),
    )
