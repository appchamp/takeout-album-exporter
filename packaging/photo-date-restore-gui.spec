# -*- mode: python ; coding: utf-8 -*-
from importlib.metadata import version as _pkg_version
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata


a = Analysis(
    [str(Path(SPECPATH).parent / "photo_date_restore/gui/launcher.py")],
    pathex=[],
    binaries=[],
    datas=copy_metadata("photo-date-restore"),
    hiddenimports=["photo_date_restore.gui.app"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    [],
    name="Photo Date Restore",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    exclude_binaries=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="Photo Date Restore",
)
# Single-sourced from the installed package metadata, so the bundle version
# never drifts from pyproject.toml / photo_date_restore.__version__.
_app_version = _pkg_version("photo-date-restore")

app = BUNDLE(
    coll,
    name="Photo Date Restore.app",
    icon=None,
    bundle_identifier="jp.ac.kyoto-u.cseas.photo-date-restore",
    info_plist={
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
        "CFBundleShortVersionString": _app_version,
        "CFBundleVersion": _app_version,
        "NSHumanReadableCopyright": "Copyright (c) 2026 Kimiya Kitani. MIT License.",
    },
)
