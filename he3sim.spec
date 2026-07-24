# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['src/he3sim/cli.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('configs/*.yaml', 'configs'),
        ('configs/schemas/*.json', 'configs/schemas'),
    ],
    hiddenimports=[
        'scipy.signal',
        'scipy.optimize',
        'scipy.fft',
        'scipy.fftpack',
        'scipy.linalg',
        'scipy.special',
        'h5py.defs',
        'h5py.utils',
        'h5py.h5ac',
        'h5py._proxy',
        'pydantic.deprecated.decorator',
        'matplotlib.backends.backend_agg',
        'yaml',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='he3-pulse-sim',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
