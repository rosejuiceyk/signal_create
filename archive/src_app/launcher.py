"""Local Streamlit launcher used by the ``he3sim web`` command."""

from __future__ import annotations

import sys
from pathlib import Path


def launch_local_web(*, port: int = 8501, headless: bool = False) -> None:
    """Run the bundled Streamlit page on the loopback interface."""
    if not 1 <= port <= 65535:
        raise ValueError("port must be within [1, 65535]")
    from streamlit.web import cli as streamlit_cli

    app_path = Path(__file__).with_name("streamlit_app.py")
    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--server.address",
        "127.0.0.1",
        "--server.port",
        str(port),
        "--server.headless",
        str(headless).lower(),
    ]
    raise SystemExit(streamlit_cli.main())
