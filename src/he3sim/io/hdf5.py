"""HDF5 persistence for Phase 1 truth events and Phase 2 waveform blocks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import h5py  # type: ignore[import-untyped]
import numpy as np
import numpy.typing as npt

from he3sim import __version__
from he3sim.config import He3SimConfig, canonical_config_json, config_hash
from he3sim.physics.events import TrueEventSimulation
from he3sim.synthesis.streaming import WaveformSimulation, iter_waveform_blocks
from he3sim.types import TRUE_EVENT_DTYPE, WAVEFORM_BLOCK_INDEX_DTYPE

EVENT_UNITS = {
    "t_s": "s",
    "energy_dep_keV": "keV",
    "amplitude_peak_V": "V",
    "tau_r_s": "s",
    "tau_d_s": "s",
}

WAVEFORM_UNITS = {
    **EVENT_UNITS,
    "preclip_analog_samples": "V",
    "analog_samples": "V",
    "adc_samples": "code",
    "t_start_s": "s",
    "sample_rate_hz": "Hz",
}


def write_true_events_hdf5(
    output_path: str | Path,
    simulation: TrueEventSimulation,
    config: He3SimConfig,
) -> Path:
    """Write a minimal, self-describing truth-event HDF5 file atomically."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")

    try:
        with h5py.File(temporary_path, "w") as handle:
            metadata = handle.create_group("metadata")
            string_dtype = h5py.string_dtype(encoding="utf-8")
            metadata.create_dataset(
                "config_json",
                data=canonical_config_json(config),
                dtype=string_dtype,
            )
            metadata.attrs["config_hash"] = config_hash(config)
            metadata.attrs["code_version"] = __version__
            metadata.attrs["seed"] = simulation.seed
            metadata.attrs["parameter_status"] = simulation.parameter_status.value
            metadata.attrs["units_json"] = json.dumps(EVENT_UNITS, sort_keys=True)
            metadata.attrs["arrival_algorithm"] = simulation.arrival_algorithm.value
            metadata.attrs["true_rate_cps"] = simulation.true_rate_cps
            metadata.attrs["duration_s"] = simulation.duration_s

            events_group = handle.create_group("events")
            events_group.create_dataset(
                "true",
                data=simulation.events,
                dtype=TRUE_EVENT_DTYPE,
                maxshape=(None,),
                chunks=True,
                compression="gzip",
                shuffle=True,
            )
        temporary_path.replace(path)
    except Exception:
        if temporary_path.exists():
            temporary_path.unlink()
        raise
    return path


def read_true_events_hdf5(
    input_path: str | Path,
) -> tuple[npt.NDArray[np.void], dict[str, Any]]:
    """Read the Phase 1 truth-event table and normalized metadata for validation."""
    path = Path(input_path)
    with h5py.File(path, "r") as handle:
        events = np.asarray(handle["events/true"], dtype=TRUE_EVENT_DTYPE)
        metadata_group = handle["metadata"]
        config_json_value = metadata_group["config_json"][()]
        if isinstance(config_json_value, bytes):
            config_json_value = config_json_value.decode("utf-8")
        metadata: dict[str, Any] = {
            "config_json": str(config_json_value),
            **{key: metadata_group.attrs[key] for key in metadata_group.attrs},
        }
    for key, value in list(metadata.items()):
        if isinstance(value, bytes):
            metadata[key] = value.decode("utf-8")
        elif isinstance(value, np.generic):
            metadata[key] = value.item()
    return events, metadata


def write_waveform_hdf5(
    output_path: str | Path,
    simulation: WaveformSimulation,
    config: He3SimConfig,
) -> Path:
    """Stream bounded continuous blocks into an atomic Phase 2 HDF5 file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    chunk_length = min(simulation.block_size, simulation.sample_count)
    block_count = (simulation.sample_count + simulation.block_size - 1) // simulation.block_size

    try:
        with h5py.File(temporary_path, "w") as handle:
            metadata = handle.create_group("metadata")
            string_dtype = h5py.string_dtype(encoding="utf-8")
            metadata.create_dataset(
                "config_json",
                data=canonical_config_json(config),
                dtype=string_dtype,
            )
            metadata.attrs["config_hash"] = config_hash(config)
            metadata.attrs["code_version"] = __version__
            metadata.attrs["seed"] = simulation.true_events.seed
            metadata.attrs["parameter_status"] = simulation.parameter_status.value
            metadata.attrs["units_json"] = json.dumps(WAVEFORM_UNITS, sort_keys=True)
            metadata.attrs["arrival_algorithm"] = simulation.true_events.arrival_algorithm.value
            metadata.attrs["renderer"] = simulation.renderer.value
            metadata.attrs["true_rate_cps"] = simulation.true_events.true_rate_cps
            metadata.attrs["event_horizon_s"] = simulation.true_events.duration_s
            metadata.attrs["sample_rate_hz"] = simulation.sample_rate_hz
            metadata.attrs["sample_count"] = simulation.sample_count
            metadata.attrs["block_size"] = simulation.block_size

            events_group = handle.create_group("events")
            events_group.create_dataset(
                "true",
                data=simulation.true_events.events,
                dtype=TRUE_EVENT_DTYPE,
                maxshape=(None,),
                chunks=True,
                compression="gzip",
                shuffle=True,
            )

            blocks = handle.create_group("blocks")
            preclip_analog_dataset = None
            analog_dataset = None
            if config.waveform.save_analog:
                preclip_analog_dataset = blocks.create_dataset(
                    "preclip_analog_samples",
                    shape=(simulation.sample_count,),
                    dtype=np.float32,
                    chunks=(chunk_length,),
                    compression="gzip",
                    shuffle=True,
                )
                analog_dataset = blocks.create_dataset(
                    "analog_samples",
                    shape=(simulation.sample_count,),
                    dtype=np.float32,
                    chunks=(chunk_length,),
                    compression="gzip",
                    shuffle=True,
                )
            adc_dataset = None
            if config.adc.enabled:
                adc_dataset = blocks.create_dataset(
                    "adc_samples",
                    shape=(simulation.sample_count,),
                    dtype=np.uint16,
                    chunks=(chunk_length,),
                    compression="gzip",
                    shuffle=True,
                )
            saturation_dataset = blocks.create_dataset(
                "saturation_mask",
                shape=(simulation.sample_count,),
                dtype=np.bool_,
                chunks=(chunk_length,),
                compression="gzip",
                shuffle=True,
            )
            index_dataset = blocks.create_dataset(
                "index",
                shape=(block_count,),
                dtype=WAVEFORM_BLOCK_INDEX_DTYPE,
            )
            event_counts = np.bincount(
                simulation.true_events.events["block_id"],
                minlength=block_count,
            )

            written_blocks = 0
            for block in iter_waveform_blocks(simulation, config):
                start = block.sample_index_start
                arrays = [
                    array
                    for array in (
                        block.preclip_analog_samples_V,
                        block.analog_samples_V,
                        block.adc_samples,
                        block.saturation_mask,
                    )
                    if array is not None
                ]
                length = arrays[0].size
                stop = start + length
                if preclip_analog_dataset is not None:
                    if block.preclip_analog_samples_V is None:
                        raise RuntimeError(
                            "pre-clipping analog output was configured but block data are missing"
                        )
                    preclip_analog_dataset[start:stop] = block.preclip_analog_samples_V
                if analog_dataset is not None:
                    if block.analog_samples_V is None:
                        raise RuntimeError(
                            "analog output was configured but block data are missing"
                        )
                    analog_dataset[start:stop] = block.analog_samples_V
                if adc_dataset is not None:
                    if block.adc_samples is None:
                        raise RuntimeError("ADC output was configured but block data are missing")
                    adc_dataset[start:stop] = block.adc_samples
                if block.saturation_mask is None:
                    raise RuntimeError("waveform block is missing its saturation mask")
                saturation_dataset[start:stop] = block.saturation_mask
                event_count = int(event_counts[block.block_id])
                index_dataset[written_blocks] = (
                    block.block_id,
                    start,
                    length,
                    block.t_start_s,
                    block.sample_rate_hz,
                    event_count,
                )
                written_blocks += 1
            if written_blocks != block_count:
                raise RuntimeError(f"wrote {written_blocks} blocks but expected {block_count}")
        temporary_path.replace(path)
    except Exception:
        if temporary_path.exists():
            temporary_path.unlink()
        raise
    return path


def inspect_hdf5(input_path: str | Path) -> dict[str, dict[str, Any]]:
    """Return dataset shapes/dtypes and metadata attributes without loading waveforms."""
    summary: dict[str, dict[str, Any]] = {}
    with h5py.File(Path(input_path), "r") as handle:

        def visitor(name: str, item: h5py.Group | h5py.Dataset) -> None:
            if isinstance(item, h5py.Dataset):
                summary[f"/{name}"] = {
                    "kind": "dataset",
                    "shape": list(item.shape),
                    "dtype": str(item.dtype),
                }
            else:
                attributes: dict[str, Any] = {}
                for key, value in item.attrs.items():
                    if isinstance(value, bytes):
                        attributes[key] = value.decode("utf-8")
                    elif isinstance(value, np.generic):
                        attributes[key] = value.item()
                    else:
                        attributes[key] = value
                summary[f"/{name}" if name else "/"] = {
                    "kind": "group",
                    "attributes": attributes,
                }

        handle.visititems(visitor)
        root_attributes = {
            key: value.item() if isinstance(value, np.generic) else value
            for key, value in handle.attrs.items()
        }
        summary["/"] = {"kind": "group", "attributes": root_attributes}
    return summary
