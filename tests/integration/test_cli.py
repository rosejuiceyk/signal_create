from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from he3sim.cli import app

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER = CliRunner()


def test_validate_config_accepts_demo_and_provisional_files() -> None:
    for name in ("demo_minimal.yaml", "provisional_he3.yaml"):
        result = RUNNER.invoke(
            app,
            ["validate-config", "-c", str(PROJECT_ROOT / "configs" / name)],
        )
        assert result.exit_code == 0, result.output
        assert "valid configuration" in result.output
        assert "config_hash:" in result.output


def test_validate_config_rejects_invalid_yaml(tmp_path: Path) -> None:
    invalid_path = tmp_path / "invalid.yaml"
    invalid_path.write_text("simulation: [not, a, mapping]\n", encoding="utf-8")

    result = RUNNER.invoke(app, ["validate-config", "-c", str(invalid_path)])

    assert result.exit_code == 2
    assert "invalid configuration" in result.output


def test_cli_accepts_windows_style_path_object() -> None:
    config_path = PROJECT_ROOT / "configs" / "demo_minimal.yaml"
    result = RUNNER.invoke(app, ["validate-config", "--config", str(config_path.resolve())])

    assert result.exit_code == 0, result.output
