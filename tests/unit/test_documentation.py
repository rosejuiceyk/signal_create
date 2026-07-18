from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_markdown_is_utf8_and_uses_supported_display_math_delimiters() -> None:
    markdown_files = sorted(PROJECT_ROOT.rglob("*.md"))
    assert markdown_files

    for path in markdown_files:
        text = path.read_text(encoding="utf-8")
        assert "�" not in text, f"replacement character found in {path}"
        assert "\\[" not in text, f"unsupported display-math opener found in {path}"
        assert "\\]" not in text, f"unsupported display-math closer found in {path}"

        delimiters = [line for line in text.splitlines() if line.strip() == "$$"]
        assert len(delimiters) % 2 == 0, f"unpaired display-math delimiter in {path}"
        assert all(line == "$$" for line in delimiters), (
            f"display-math delimiter must occupy its own line in {path}"
        )


def test_retired_web_and_ml_routes_are_archived() -> None:
    """Retired routes must remain auditable without being active package modules."""
    for active_path in (
        PROJECT_ROOT / "src" / "he3sim" / "app",
        PROJECT_ROOT / "src" / "he3sim" / "ml",
        PROJECT_ROOT / "docs" / "phases" / "phase_03_5_local_web.md",
        PROJECT_ROOT / "docs" / "phases" / "phase_05_network_a.md",
        PROJECT_ROOT / "docs" / "phases" / "phase_06_network_c.md",
    ):
        assert not active_path.exists()

    for archived_path in (
        PROJECT_ROOT / "archive" / "src_app",
        PROJECT_ROOT / "archive" / "src_ml",
        PROJECT_ROOT / "archive" / "docs_phases" / "phase_03_5_local_web.md",
        PROJECT_ROOT / "archive" / "docs_phases" / "phase_05_network_a.md",
        PROJECT_ROOT / "archive" / "docs_phases" / "phase_06_network_c.md",
    ):
        assert archived_path.exists()


def test_active_cli_and_docs_do_not_advertise_archived_commands() -> None:
    """Active entry points must not leave users on archived Web or ML paths."""
    active_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            PROJECT_ROOT / "src" / "he3sim" / "cli.py",
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "docs" / "SOFTWARE_USER_MANUAL.md",
        )
    )
    for command in (
        "he3sim web",
        "train-event-model",
        "compare-event-model",
        "rehearse-residual-model",
    ):
        assert command not in active_text

    assert (PROJECT_ROOT / "docs" / "ROADMAP_v2.md").exists()
