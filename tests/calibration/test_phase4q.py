from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from typer.testing import CliRunner

from he3sim.calibration.models import QCStatus, WaveformVariant
from he3sim.calibration.probe import iter_waveform_records
from he3sim.calibration.profile import load_acquisition_profile
from he3sim.calibration.qualification import qualify_acquisition
from he3sim.calibration.quality import duplicate_metrics, evaluate_event_qc
from he3sim.cli import app

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = PROJECT_ROOT / "configs" / "acquisition_profiles" / "dt5790_run3.yaml"


def _write_run(root: Path, run_id: str, rows: list[list[int]], rate_cps: float) -> None:
    run = root / run_id
    run.mkdir(parents=True)
    (run / f"{run_id}_info.txt").write_text(
        f"Run ID = {run_id}\nInput counts = {len(rows)}; average rate (cps) = {rate_cps}\n",
        encoding="gb18030",
    )
    (run / "settings.xml").write_text(
        "<settings><sampleTime>4000</sampleTime><energyMaxBits>15</energyMaxBits>"
        "<parameter><key>SRV_PARAM_CH_POLARITY</key>"
        "<value><value>POLARITY_POSITIVE</value></value></parameter></settings>",
        encoding="utf-8",
    )
    header = "BOARD;CHANNEL;TIMETAG;ENERGY;ENERGYSHORT;FLAGS;PROBE_CODE;SAMPLES\n"
    for directory, prefix in (
        ("RAW", "DataR"),
        ("FILTERED", "DataF"),
        ("UNFILTERED", "Data"),
    ):
        folder = run / directory
        folder.mkdir()
        body = []
        for index, samples in enumerate(rows):
            metadata = ["0", "0", str(index), "100", "50", "0x0", "1"]
            body.append(";".join(metadata + [str(value) for value in samples]))
        text = header + ("\n".join(body) + "\n" if body else "")
        (folder / f"{prefix}_{run_id}.CSV").write_text(text, encoding="utf-8")


def _paired_pulse() -> list[int]:
    return [10, 10, 10, 10, 12, 12, 20, 20, 30, 30, 20, 20, 12, 12, 10, 10]


def test_profile_and_streaming_probe_preserve_exported_samples(tmp_path: Path) -> None:
    _write_run(tmp_path, "run3_1", [_paired_pulse()], 10.0)
    profile = load_acquisition_profile(PROFILE_PATH)
    raw_path = next((tmp_path / "run3_1" / "RAW").glob("*.CSV"))

    records = list(iter_waveform_records(raw_path, profile, WaveformVariant.RAW))

    assert len(records) == 1
    assert records[0].metadata["TIMETAG"] == "0"
    assert records[0].samples_ADC_counts.tolist() == _paired_pulse()


def test_qc_uses_four_states_and_never_deduplicates() -> None:
    profile = load_acquisition_profile(PROFILE_PATH)
    samples = np.asarray(_paired_pulse(), dtype=np.int64)

    result = evaluate_event_qc(samples, polarity=1, thresholds=profile.qc)

    assert result.statuses["duplicate_samples"] is QCStatus.FAIL
    assert result.statuses["saturation"] is QCStatus.NOT_EVALUABLE
    assert result.statuses["low_amplitude"] is QCStatus.PASS
    assert result.metrics["sample_interval_s"] is None
    assert duplicate_metrics(samples).candidate_deduplicated_sample_count == samples.size // 2
    assert samples.tolist() == _paired_pulse()


def test_missing_polarity_is_not_silently_inferred() -> None:
    profile = load_acquisition_profile(PROFILE_PATH)
    result = evaluate_event_qc(
        np.asarray(_paired_pulse(), dtype=np.int64), polarity=None, thresholds=profile.qc
    )

    assert result.statuses["tail_truncated"] is QCStatus.NOT_EVALUABLE
    assert result.statuses["trigger_clipped"] is QCStatus.NOT_EVALUABLE


def test_qualification_is_read_only_and_reports_blocked_split(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    pulse = _paired_pulse()
    _write_run(source, "run3_1", [], 0.0)
    _write_run(source, "run3_2", [pulse, pulse], 10.0)
    before = {
        path.relative_to(source).as_posix(): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_mtime_ns,
        )
        for path in source.rglob("*")
        if path.is_file()
    }

    artifacts = qualify_acquisition(source, PROFILE_PATH, output, max_events_per_run=1)

    after = {
        path.relative_to(source).as_posix(): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_mtime_ns,
        )
        for path in source.rglob("*")
        if path.is_file()
    }
    assert before == after
    assert artifacts.run_count == 2
    assert artifacts.signal_run_count == 1
    assert artifacts.processed_event_count == 1
    assert artifacts.scan_complete_run_count == 1
    assert artifacts.scientific_exit_blocked
    provenance = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["source_metadata_unchanged"] is True
    assert provenance["source_tree_file_count"] == len(before)
    split = json.loads(artifacts.split_feasibility_path.read_text(encoding="utf-8"))
    assert split["split_feasible"] is False
    event = json.loads(artifacts.event_qc_path.read_text(encoding="utf-8").splitlines()[0])
    assert event["label_status"] == "unknown"
    assert event["sample_interval_s"] is None
    assert event["qc"]["duplicate_samples"] == "fail"


def test_cli_qualifies_fixture_and_network_a_commands_are_retired(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    _write_run(source, "run3_1", [_paired_pulse()], 10.0)
    runner = CliRunner()

    help_result = runner.invoke(app, ["--help"])
    result = runner.invoke(
        app,
        [
            "qualify-acquisition",
            "--input",
            str(source),
            "--profile",
            str(PROFILE_PATH),
            "--output",
            str(output),
            "--max-events-per-run",
            "1",
        ],
    )

    assert help_result.exit_code == 0
    assert "train-event-model" not in help_result.output
    assert "compare-event-model" not in help_result.output
    assert result.exit_code == 0, result.output
    assert "scientific_exit_blocked: true" in result.output
    assert (output / "provenance.json").exists()
