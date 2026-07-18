from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = PROJECT_ROOT / "src" / "he3sim" / "app" / "streamlit_app.py"


def test_streamlit_page_loads_and_generates_small_waveform(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "HE3SIM_WEB_BASE_CONFIG",
        str(PROJECT_ROOT / "configs" / "demo_minimal.yaml"),
    )
    monkeypatch.setenv("HE3SIM_WEB_OUTPUT_ROOT", str(tmp_path))
    app = AppTest.from_file(str(APP_PATH)).run(timeout=30)

    assert not app.exception
    assert app.title[0].value == "He-3 连续波形生成器"
    assert not app.warning
    assert len(app.number_input) == 4
    assert len(app.button) == 1
    captions = {caption.value for caption in app.caption}
    assert "允许范围：10～10,000,000 cps" in captions
    assert "允许范围：100～250 MS/s" in captions
    assert "允许范围：0～2,147,483,647" in captions
    assert any("允许范围：0.001～19.999996 ms" in caption for caption in captions)
    assert any("当前最大：19.999996 ms" in caption.value for caption in app.caption)

    app.number_input[0].set_value(100_000.0)
    app.number_input[1].set_value(100.0)
    app.number_input[2].set_value(0.01)
    app.number_input[3].set_value(20_260_711)
    app.button[0].click().run(timeout=60)

    assert not app.exception
    assert app.success[0].value == "连续波形生成完成"
    assert len(app.dataframe) == 1
    assert "参数状态" not in {metric.label for metric in app.metric}
    assert len(list(tmp_path.glob("web-*/waveform.h5"))) == 1
    assert len(list(tmp_path.glob("web-*/waveform.csv"))) == 1


def test_web_cli_help_is_available() -> None:
    from typer.testing import CliRunner

    from he3sim.cli import app

    result = CliRunner().invoke(app, ["web", "--help"])

    assert result.exit_code == 0, result.output
    assert "127.0.0.1" in result.output
