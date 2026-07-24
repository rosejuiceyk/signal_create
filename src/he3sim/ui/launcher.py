"""Windowed launcher for the portable He3Signal application."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import TextIO

from he3sim.ui.runtime import application_root, resource_path

APP_NAME = "He3Signal"
HOST = "127.0.0.1"
RUNTIME_FILE = ".he3signal-runtime.json"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def _server_is_ready(port: int, timeout_s: float = 0.15) -> bool:
    try:
        with socket.create_connection((HOST, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _read_running_port(runtime_file: Path) -> int | None:
    try:
        payload = json.loads(runtime_file.read_text(encoding="utf-8"))
        port = int(payload["port"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    return port if 0 < port < 65536 and _server_is_ready(port) else None


def _server_command(port: int) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--streamlit-server", str(port)]
    return [sys.executable, "-m", "he3sim.ui.launcher", "--streamlit-server", str(port)]


def _streamlit_flags(port: int) -> dict[str, object]:
    return {
        "global_developmentMode": False,
        "server_address": HOST,
        "server_port": port,
        "server_headless": True,
        "server_fileWatcherType": "none",
        "server_enableCORS": True,
        "server_enableXsrfProtection": True,
        "browser_gatherUsageStats": False,
    }


def _run_streamlit_server(port: int) -> None:
    from streamlit.web import bootstrap

    root = application_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / "outputs").mkdir(exist_ok=True)
    os.chdir(root)

    app_path = resource_path("he3sim/ui/app.py")
    if not app_path.is_file():
        raise FileNotFoundError(f"UI entry point not found: {app_path}")

    flags = _streamlit_flags(port)
    bootstrap.load_config_options(flag_options=flags)
    bootstrap.run(str(app_path), False, [], flags)


def _open_existing_instance(runtime_file: Path) -> bool:
    port = _read_running_port(runtime_file)
    if port is None:
        return False
    webbrowser.open(f"http://{HOST}:{port}")
    return True


def _start_server_process(port: int, log_handle: TextIO) -> subprocess.Popen[str]:
    creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    return subprocess.Popen(
        _server_command(port),
        cwd=application_root(),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=creation_flags,
    )


def _run_windowed_launcher() -> None:
    import tkinter as tk
    from tkinter import messagebox

    root_dir = application_root()
    root_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = root_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    runtime_file = root_dir / RUNTIME_FILE

    if _open_existing_instance(runtime_file):
        return

    port = _find_free_port()
    log_handle = (logs_dir / "launcher.log").open("a", encoding="utf-8")
    process = _start_server_process(port, log_handle)

    window = tk.Tk()
    window.title("He3Signal 启动控制器")
    window.geometry("440x190")
    window.resizable(False, False)

    title = tk.Label(window, text="He-3 脉冲信号模拟系统", font=("Microsoft YaHei UI", 15, "bold"))
    title.pack(pady=(24, 8))
    status_text = tk.StringVar(value="正在启动本地服务，请稍候……")
    status = tk.Label(window, textvariable=status_text, font=("Microsoft YaHei UI", 10))
    status.pack(pady=4)

    button_frame = tk.Frame(window)
    button_frame.pack(pady=18)
    opened = False
    closing = False

    def open_interface() -> None:
        webbrowser.open(f"http://{HOST}:{port}")

    open_button = tk.Button(
        button_frame,
        text="打开界面",
        command=open_interface,
        width=14,
        state=tk.DISABLED,
    )
    open_button.pack(side=tk.LEFT, padx=8)

    def close_application() -> None:
        nonlocal closing
        if closing:
            return
        closing = True
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        try:
            runtime_file.unlink(missing_ok=True)
        finally:
            log_handle.close()
            window.destroy()

    close_button = tk.Button(
        button_frame,
        text="退出软件",
        command=close_application,
        width=14,
    )
    close_button.pack(side=tk.LEFT, padx=8)
    window.protocol("WM_DELETE_WINDOW", close_application)

    def poll_server() -> None:
        nonlocal opened
        if closing:
            return
        if process.poll() is not None:
            status_text.set("启动失败，请查看 logs/launcher.log")
            messagebox.showerror(
                APP_NAME,
                "本地服务启动失败。请查看软件目录下的 logs/launcher.log。",
            )
            close_application()
            return
        if _server_is_ready(port):
            runtime_file.write_text(
                json.dumps({"pid": process.pid, "port": port}),
                encoding="utf-8",
            )
            status_text.set("软件正在运行。关闭本窗口即可停止服务。")
            open_button.configure(state=tk.NORMAL)
            if not opened:
                opened = True
                open_interface()
                window.after(700, window.iconify)
            return
        window.after(200, poll_server)

    window.after(100, poll_server)
    window.mainloop()


def main() -> None:
    """Run either the internal server process or the windowed launcher."""

    if len(sys.argv) == 3 and sys.argv[1] == "--streamlit-server":
        _run_streamlit_server(int(sys.argv[2]))
        return
    _run_windowed_launcher()


if __name__ == "__main__":
    main()
