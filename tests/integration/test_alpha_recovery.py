from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from he3sim.cli import app


def test_analyze_noise_cli_writes_static_report(tmp_path: Path) -> None:
    output = tmp_path / "phase_b"
    result = CliRunner().invoke(
        app,
        [
            "analyze-noise",
            "-c",
            "configs/demo_minimal.yaml",
            "-o",
            str(output),
            "--target-events",
            "20000",
            "--bootstrap-replicates",
            "2",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (output / "phase_b_noise.html").exists()
    payload = json.loads((output / "phase_b_noise.json").read_text(encoding="utf-8"))
    assert set(payload["fits"]) == {"Rossi-alpha", "Feynman-alpha", "PSD"}
    assert all(
        fit["alpha_std_per_s"] > fit["naive_alpha_std_per_s"] for fit in payload["fits"].values()
    )
    assert len(list(output.glob("*.png"))) == 3
    html = (output / "phase_b_noise.html").read_text(encoding="utf-8")
    assert "普通图注使用中文" in html
