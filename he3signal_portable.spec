# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

streamlit_datas = collect_data_files("streamlit")
streamlit_hiddenimports = collect_submodules(
    "streamlit",
    filter=lambda name: not name.startswith(("streamlit.hello", "streamlit.testing")),
)
he3sim_hiddenimports = collect_submodules("he3sim")

datas = streamlit_datas + copy_metadata("streamlit") + [
    ("src/he3sim/ui/app.py", "he3sim/ui"),
    ("src/he3sim/ui/pages", "he3sim/ui/pages"),
    ("configs", "configs"),
    ("PORTABLE_README.txt", "."),
]

a = Analysis(
    ["src/he3sim/ui/launcher.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=streamlit_hiddenimports + he3sim_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "bokeh",
        "IPython",
        "jax",
        "jaxlib",
        "jupyter",
        "keras",
        "mypy",
        "notebook",
        "plotly",
        "pytest",
        "ruff",
        "sklearn",
        "sympy",
        "tensorboard",
        "tensorflow",
        "torch",
        "torchaudio",
        "torchvision",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="He3Signal",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="He3Signal",
)
