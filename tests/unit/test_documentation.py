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


def test_phase5_manual_commands_pin_environment_and_project_root() -> None:
    """Phase 5 review commands must not depend on the outer cwd or a global entry point."""

    manual = (PROJECT_ROOT / "docs" / "USER_MANUAL.md").read_text(encoding="utf-8")
    phase5 = manual.split("## 9. Phase 5", maxsplit=1)[1].split("## 10. 如何提交", maxsplit=1)[0]

    assert "Set-Location .\\he3_codex_context" in phase5
    assert "Test-Path .\\pyproject.toml" in phase5
    assert (
        "conda run -n signal_create python -m he3sim train-event-model -c configs/ml_event.yaml"
    ) in phase5
    assert (
        "conda run -n signal_create python -m he3sim compare-event-model "
        "-c configs/ml_event_eval.yaml -o outputs/phase05_comparison"
    ) in phase5
    assert "he3sim compare-event-model `" not in phase5
