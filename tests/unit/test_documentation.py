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
