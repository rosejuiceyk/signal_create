"""Phase 4Q orchestration for read-only run qualification and gap reporting."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import numpy as np

from he3sim.calibration.models import (
    LabelStatus,
    RunUsability,
    SamplingAxisStatus,
    WaveformVariant,
)
from he3sim.calibration.probe import (
    discover_variant_files,
    iter_waveform_records,
    parse_info_file,
    parse_polarity,
    parse_settings_file,
    sha256_file,
)
from he3sim.calibration.profile import (
    acquisition_profile_hash,
    load_acquisition_profile,
)
from he3sim.calibration.quality import evaluate_event_qc


@dataclass(frozen=True, slots=True)
class QualificationArtifacts:
    """Paths and summary counters produced by one qualification run."""

    output_directory: Path
    run_manifest_path: Path
    event_qc_path: Path
    sampling_axis_report_path: Path
    split_feasibility_path: Path
    gap_report_path: Path
    run_count: int
    signal_run_count: int
    processed_event_count: int
    scan_complete_run_count: int
    scientific_exit_blocked: bool


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _single_match(directory: Path, pattern: str, description: str) -> Path | None:
    matches = sorted(directory.glob(pattern))
    if len(matches) > 1:
        raise ValueError(f"multiple {description} files found in {directory}")
    return matches[0] if matches else None


def _run_sort_key(path: Path) -> tuple[int, str]:
    suffix = path.name.rsplit("_", maxsplit=1)[-1]
    return (int(suffix), path.name) if suffix.isdigit() else (2**31 - 1, path.name)


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _package_version() -> str:
    try:
        return version("he3-pulse-sim")
    except PackageNotFoundError:
        return "uninstalled"


def _ensure_output_outside_source(input_root: Path, output_directory: Path) -> None:
    source = input_root.resolve()
    output = output_directory.resolve()
    if output == source or source in output.parents:
        raise ValueError("Phase 4Q output_directory must be outside the read-only source tree")


def _source_metadata_snapshot(input_root: Path) -> dict[str, tuple[int, int]]:
    """Capture a cheap source-tree size/mtime snapshot without reading file contents."""
    return {
        path.relative_to(input_root).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in input_root.rglob("*")
        if path.is_file()
    }


def _file_row(
    input_root: Path,
    run_id: str,
    kind: str,
    variant: str,
    path: Path,
) -> dict[str, Any]:
    stat = path.stat()
    return {
        "run_id": run_id,
        "kind": kind,
        "waveform_variant": variant,
        "relative_path": path.relative_to(input_root).as_posix(),
        "size_bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
        "sha256": sha256_file(path),
    }


def _event_payload(
    run_id: str,
    waveform_variant: WaveformVariant,
    source_relative_path: str,
    source_sha256: str,
    record_metadata: dict[str, str],
    event_index: int,
    result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "event_index": event_index,
        "waveform_variant": waveform_variant.value,
        "source_relative_path": source_relative_path,
        "source_sha256": source_sha256,
        "timetag_raw": record_metadata.get("TIMETAG"),
        "energy_channel_raw": record_metadata.get("ENERGY"),
        "flags_raw": record_metadata.get("FLAGS"),
        "particle_label_raw": None,
        "label_status": LabelStatus.UNKNOWN.value,
        "sampling_axis_status": SamplingAxisStatus.UNCONFIRMED.value,
        "sample_interval_s": None,
        **result,
    }


def _write_sampling_report(
    output_directory: Path,
    duplicate_fractions: list[float],
    sampled_event_count: int,
) -> tuple[Path, Path]:
    report = {
        "sampling_axis_status": SamplingAxisStatus.UNCONFIRMED.value,
        "sample_interval_s": None,
        "sampled_event_count": sampled_event_count,
        "mean_even_pair_equal_fraction": (
            float(np.mean(duplicate_fractions)) if duplicate_fractions else None
        ),
        "minimum_even_pair_equal_fraction": (
            float(np.min(duplicate_fractions)) if duplicate_fractions else None
        ),
        "maximum_even_pair_equal_fraction": (
            float(np.max(duplicate_fractions)) if duplicate_fractions else None
        ),
        "candidate_hypotheses": [
            "each exported value is one physical sample",
            "each exact adjacent pair represents one physical sample",
        ],
        "required_external_evidence": (
            "Acquire at least two known-frequency signals through the same export path and compare "
            "the inferred frequency under both hypotheses; do not fit physical time constants "
            "first."
        ),
    }
    json_path = output_directory / "sampling_axis_report.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path = output_directory / "sampling_axis_report.md"
    md_path.write_text(
        "# Phase 4Q sampling-axis report\n\n"
        f"- Status: `{report['sampling_axis_status']}`\n"
        f"- Physical sample interval: `{report['sample_interval_s']}`\n"
        f"- Sampled events: {sampled_event_count}\n"
        f"- Mean exact even-pair fraction: {report['mean_even_pair_equal_fraction']}\n\n"
        "The existing export cannot distinguish copying, firmware upsampling, or valid repeated "
        "samples. A controlled known-frequency acquisition is required. No deduplication or "
        "seconds-based timing is authorized.\n",
        encoding="utf-8",
    )
    return json_path, md_path


def qualify_acquisition(
    input_root: str | Path,
    profile_path: str | Path,
    output_directory: str | Path,
    *,
    max_events_per_run: int | None = 256,
) -> QualificationArtifacts:
    """Qualify run exports without modifying, copying, or calibrating source waveforms."""
    source_root = Path(input_root)
    output = Path(output_directory)
    if not source_root.is_dir():
        raise ValueError(f"input_root is not a directory: {source_root}")
    if max_events_per_run is not None and max_events_per_run <= 0:
        raise ValueError("max_events_per_run must be positive or None")
    _ensure_output_outside_source(source_root, output)
    profile = load_acquisition_profile(profile_path)
    source_snapshot_before = _source_metadata_snapshot(source_root)
    output.mkdir(parents=True, exist_ok=True)

    run_directories = sorted(source_root.glob(profile.run_glob), key=_run_sort_key)
    if not run_directories:
        raise ValueError(f"no run directories match {profile.run_glob!r}")

    file_rows: list[dict[str, Any]] = []
    run_rows: list[dict[str, Any]] = []
    qc_counts: Counter[str] = Counter()
    duplicate_fractions: list[float] = []
    processed_event_count = 0
    signal_run_count = 0
    scan_complete_run_count = 0
    event_qc_path = output / "event_qc.jsonl"

    with event_qc_path.open("w", encoding="utf-8", newline="\n") as event_handle:
        for run_directory in run_directories:
            if not run_directory.is_dir():
                continue
            run_id = run_directory.name
            variant_files = discover_variant_files(run_directory, profile)
            info_path = _single_match(run_directory, profile.info_file_glob, "run info")
            settings_path = _single_match(run_directory, profile.settings_file_glob, "settings")
            if info_path is None or settings_path is None:
                raise ValueError(f"missing run info or settings XML in {run_directory}")

            run_file_rows = [
                _file_row(source_root, run_id, "run_info", "", info_path),
                _file_row(source_root, run_id, "settings", "", settings_path),
            ]
            for variant, path in variant_files.items():
                if path is not None:
                    run_file_rows.append(
                        _file_row(source_root, run_id, "waveform", variant.value, path)
                    )
            file_rows.extend(run_file_rows)
            file_hash_by_path = {
                str(source_root / row["relative_path"]): str(row["sha256"]) for row in run_file_rows
            }

            info = parse_info_file(info_path, profile)
            settings = parse_settings_file(settings_path, profile)
            polarity = parse_polarity(settings)
            input_count = _parse_int(info.get("input_count"))
            declared_rate_cps = _parse_float(info.get("input_rate_cps"))
            primary_path = variant_files[profile.primary_variant]
            processed = 0
            scan_truncated = False
            run_qc_counts: Counter[str] = Counter()
            if primary_path is not None:
                source_relative = primary_path.relative_to(source_root).as_posix()
                source_hash = file_hash_by_path[str(primary_path)]
                for record in iter_waveform_records(primary_path, profile, profile.primary_variant):
                    if max_events_per_run is not None and processed >= max_events_per_run:
                        scan_truncated = True
                        break
                    qc = evaluate_event_qc(record.samples_ADC_counts, polarity, profile.qc)
                    payload = _event_payload(
                        run_id,
                        profile.primary_variant,
                        source_relative,
                        source_hash,
                        record.metadata,
                        record.event_index,
                        qc.to_dict(),
                    )
                    event_handle.write(
                        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
                    )
                    processed += 1
                    processed_event_count += 1
                    duplicate_fractions.append(qc.duplicate_metrics.even_pair_equal_fraction)
                    for name, status in qc.statuses.items():
                        key = f"{name}:{status.value}"
                        run_qc_counts[key] += 1
                        qc_counts[key] += 1

            scan_complete = not scan_truncated
            if scan_complete:
                scan_complete_run_count += 1
            has_signal = bool((input_count or 0) > 0 or processed > 0)
            if has_signal:
                signal_run_count += 1
            usability = RunUsability.QC_LIMITED if has_signal else RunUsability.EMPTY
            run_rows.append(
                {
                    "run_id": run_id,
                    "declared_input_count": input_count,
                    "declared_input_rate_cps": declared_rate_cps,
                    "processed_event_count": processed,
                    "event_scan_complete": scan_complete,
                    "channel_polarity_raw": settings.get("channel_polarity_raw"),
                    "sample_time_raw": settings.get("sample_time_raw"),
                    "energy_max_bits_raw": settings.get("energy_max_bits_raw"),
                    "sampling_axis_status": SamplingAxisStatus.UNCONFIRMED.value,
                    "sample_interval_s": None,
                    "primary_variant": profile.primary_variant.value,
                    "raw_present": variant_files[WaveformVariant.RAW] is not None,
                    "filtered_present": variant_files[WaveformVariant.FILTERED] is not None,
                    "unfiltered_present": variant_files[WaveformVariant.UNFILTERED] is not None,
                    "label_status": LabelStatus.UNKNOWN.value,
                    "usability": usability.value,
                    "qc_fail_count": sum(
                        count for key, count in run_qc_counts.items() if key.endswith(":fail")
                    ),
                }
            )

    file_manifest_path = output / "file_manifest.csv"
    _write_csv(
        file_manifest_path,
        file_rows,
        [
            "run_id",
            "kind",
            "waveform_variant",
            "relative_path",
            "size_bytes",
            "mtime_utc",
            "sha256",
        ],
    )
    run_manifest_path = output / "run_manifest.csv"
    _write_csv(
        run_manifest_path,
        run_rows,
        [
            "run_id",
            "declared_input_count",
            "declared_input_rate_cps",
            "processed_event_count",
            "event_scan_complete",
            "channel_polarity_raw",
            "sample_time_raw",
            "energy_max_bits_raw",
            "sampling_axis_status",
            "sample_interval_s",
            "primary_variant",
            "raw_present",
            "filtered_present",
            "unfiltered_present",
            "label_status",
            "usability",
            "qc_fail_count",
        ],
    )
    _write_csv(
        output / "qc_summary.csv",
        [{"qc_status": key, "event_count": value} for key, value in sorted(qc_counts.items())],
        ["qc_status", "event_count"],
    )

    sampling_json_path, _ = _write_sampling_report(
        output, duplicate_fractions, processed_event_count
    )
    rates: dict[str, list[str]] = defaultdict(list)
    for row in run_rows:
        rate = row["declared_input_rate_cps"]
        if row["usability"] != RunUsability.EMPTY.value and rate is not None:
            rates[f"{float(rate):.12g}"].append(str(row["run_id"]))
    insufficient_rates = {
        rate: runs
        for rate, runs in rates.items()
        if len(runs) < profile.minimum_independent_runs_per_rate
    }
    split_report = {
        "split_unit": "acquisition_run",
        "minimum_independent_runs_per_rate": profile.minimum_independent_runs_per_rate,
        "rate_groups": rates,
        "insufficient_rate_groups": insufficient_rates,
        "split_feasible": False,
        "reason": (
            "sampling axis remains unconfirmed and current rate groups do not contain enough "
            "independent acquisition runs; no event or patch split was created"
        ),
    }
    split_feasibility_path = output / "split_feasibility.json"
    split_feasibility_path.write_text(
        json.dumps(split_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    scientific_exit_blocked = True
    gap_report_path = output / "data_gap_report.md"
    incomplete = len(run_rows) - scan_complete_run_count
    gap_report_path.write_text(
        "# Phase 4Q data-gap report\n\n"
        "## Decision\n\n"
        "`blocked`: the current data cannot enter formal calibration or residual-network "
        "training.\n\n"
        "## Blocking conditions\n\n"
        "- The physical meaning of exact adjacent sample pairs is unconfirmed.\n"
        "- The physical sample interval remains null.\n"
        "- Each current count-rate condition lacks independent train/validation/test runs.\n"
        "- Acquisition particle labels remain unknown/candidate rather than external truth.\n"
        f"- {incomplete} run scans were deliberately bounded and are not full event censuses.\n\n"
        "No energy-channel-to-keV conversion, waveform-voltage conversion, deduplication, pulse "
        "fit, or parameter calibration was performed.\n",
        encoding="utf-8",
    )

    source_snapshot_after = _source_metadata_snapshot(source_root)
    source_metadata_unchanged = source_snapshot_before == source_snapshot_after
    provenance = {
        "phase": "4Q",
        "created_at_utc": datetime.now(tz=UTC).isoformat(),
        "code_version": _package_version(),
        "input_root": str(source_root.resolve()),
        "source_access": "read_only",
        "source_files_copied": False,
        "profile_path": str(Path(profile_path).resolve()),
        "profile_hash": acquisition_profile_hash(profile),
        "profile_parameter_status": profile.parameter_status.value,
        "qc_parameter_status": profile.qc.parameter_status.value,
        "max_events_per_run": max_events_per_run,
        "profiled_source_file_count": len(file_rows),
        "profiled_source_total_bytes": sum(int(row["size_bytes"]) for row in file_rows),
        "source_tree_file_count": len(source_snapshot_before),
        "source_tree_total_bytes": sum(size for size, _ in source_snapshot_before.values()),
        "source_metadata_unchanged": source_metadata_unchanged,
        "scientific_exit_blocked": scientific_exit_blocked,
    }
    (output / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return QualificationArtifacts(
        output_directory=output,
        run_manifest_path=run_manifest_path,
        event_qc_path=event_qc_path,
        sampling_axis_report_path=sampling_json_path,
        split_feasibility_path=split_feasibility_path,
        gap_report_path=gap_report_path,
        run_count=len(run_rows),
        signal_run_count=signal_run_count,
        processed_event_count=processed_event_count,
        scan_complete_run_count=scan_complete_run_count,
        scientific_exit_blocked=scientific_exit_blocked,
    )
