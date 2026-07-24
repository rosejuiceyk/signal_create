from pathlib import Path

from he3sim.ui.launcher import _read_running_port, _server_command, _streamlit_flags
from he3sim.ui.runtime import application_root, resource_path


def test_source_runtime_paths_point_to_project_files() -> None:
    assert (application_root() / "pyproject.toml").is_file()
    assert resource_path("configs/demo_minimal.yaml").is_file()
    assert resource_path("he3sim/ui/app.py") == Path(__file__).parents[2] / "src/he3sim/ui/app.py"


def test_invalid_runtime_file_is_ignored(tmp_path: Path) -> None:
    runtime_file = tmp_path / ".he3signal-runtime.json"
    runtime_file.write_text("not-json", encoding="utf-8")

    assert _read_running_port(runtime_file) is None


def test_source_server_command_uses_module_entrypoint() -> None:
    command = _server_command(8765)

    assert command[-4:] == ["-m", "he3sim.ui.launcher", "--streamlit-server", "8765"]


def test_streamlit_flags_use_cli_names() -> None:
    flags = _streamlit_flags(8765)

    assert flags["server_address"] == "127.0.0.1"
    assert flags["server_port"] == 8765
    assert flags["global_developmentMode"] is False
    assert not any("." in name for name in flags)
