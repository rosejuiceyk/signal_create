"""Read-only, streaming probes for acquisition metadata and event waveforms."""

from __future__ import annotations

import csv
import hashlib
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from he3sim.calibration.models import WaveformRecord, WaveformVariant
from he3sim.calibration.profile import AcquisitionProfile

HASH_CHUNK_BYTES = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Hash one file incrementally without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def discover_variant_files(
    run_directory: Path, profile: AcquisitionProfile
) -> dict[WaveformVariant, Path | None]:
    """Resolve at most one file per explicit waveform version."""
    result: dict[WaveformVariant, Path | None] = {}
    for variant, rule in profile.variants.items():
        matches = sorted((run_directory / rule.directory).glob(rule.file_glob))
        if len(matches) > 1:
            raise ValueError(f"multiple {variant.value} files found in {run_directory}")
        result[variant] = matches[0] if matches else None
    return result


def iter_waveform_records(
    path: Path,
    profile: AcquisitionProfile,
    variant: WaveformVariant,
) -> Iterator[WaveformRecord]:
    """Yield one integer waveform row at a time from a delimited export."""
    with path.open("r", encoding=profile.csv_encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=profile.csv_delimiter)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"waveform file is empty: {path}") from exc
        if profile.samples_column not in header:
            raise ValueError(f"missing samples column {profile.samples_column!r}: {path}")
        sample_start = header.index(profile.samples_column)
        missing = [name for name in profile.metadata_columns if name not in header[:sample_start]]
        if missing:
            raise ValueError(f"missing metadata columns {missing}: {path}")
        metadata_indices = {name: header.index(name) for name in profile.metadata_columns}
        for event_index, row in enumerate(reader):
            if len(row) <= sample_start:
                raise ValueError(f"event row {event_index} contains no samples: {path}")
            try:
                samples = np.asarray(row[sample_start:], dtype=np.int64)
            except ValueError as exc:
                raise ValueError(f"non-integer sample in event row {event_index}: {path}") from exc
            yield WaveformRecord(
                event_index=event_index,
                source_path=path,
                variant=variant,
                metadata={name: row[index] for name, index in metadata_indices.items()},
                samples_ADC_counts=samples,
            )


def parse_info_file(path: Path, profile: AcquisitionProfile) -> dict[str, str | None]:
    """Extract only explicitly configured run-info fields."""
    text = path.read_text(encoding=profile.info_encoding)
    result: dict[str, str | None] = {}
    for name, pattern in profile.info_patterns.items():
        match = re.search(pattern, text, flags=re.MULTILINE)
        result[name] = match.group("value") if match else None
    return result


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def parse_settings_file(path: Path, profile: AcquisitionProfile) -> dict[str, str | None]:
    """Extract simple tags and configured key/value parameters from XML."""
    root = ET.parse(path).getroot()
    result: dict[str, str | None] = {}
    elements = list(root.iter())
    for output_name, tag_name in profile.xml_tags.items():
        match = next((item for item in elements if _local_name(item.tag) == tag_name), None)
        result[output_name] = match.text.strip() if match is not None and match.text else None
    for output_name, parameter_key in profile.xml_parameter_keys.items():
        value: str | None = None
        for parent in elements:
            children = list(parent)
            keyed = any(
                _local_name(child.tag) == "key"
                and child.text is not None
                and child.text.strip() == parameter_key
                for child in children
            )
            if not keyed:
                continue
            value_element = next(
                (child for child in children if _local_name(child.tag) == "value"), None
            )
            if value_element is not None:
                nested = next(
                    (
                        item
                        for item in value_element.iter()
                        if item is not value_element
                        and _local_name(item.tag) == "value"
                        and item.text is not None
                        and item.text.strip()
                    ),
                    None,
                )
                if nested is not None and nested.text is not None:
                    value = nested.text.strip()
                    break
                if value_element.text and value_element.text.strip():
                    value = value_element.text.strip()
                    break
        result[output_name] = value
    return result


def parse_polarity(settings: dict[str, str | None]) -> int | None:
    """Map an explicit exported polarity token without guessing."""
    token = settings.get("channel_polarity_raw")
    if token == "POLARITY_POSITIVE":
        return 1
    if token == "POLARITY_NEGATIVE":
        return -1
    return None
