# -*- mode: python ; coding: utf-8 -*-
"""One-folder ORION service build. Run from the build directory."""

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

hidden = (
    collect_submodules("service")
    + collect_submodules("tools")
    + collect_submodules("ai")
    + collect_submodules("faster_whisper")
    + collect_submodules("ctranslate2")
    + collect_submodules("websockets")
    + collect_submodules("web")
    + collect_submodules("core")
    + collect_submodules("voice")
    + collect_submodules("storage")
    + collect_submodules("app")
    + collect_submodules("edge_tts")
    + collect_submodules("webview")
    + ["uvicorn.protocols.websockets.websockets_impl", "app.migrate"]
)
binaries = collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("onnxruntime")
datas = [
    ("../web/dist", "web/dist"),
    ("../data/models/silero_vad.onnx", "data/models"),
] + collect_data_files("ctranslate2") + collect_data_files("kokoro_onnx") + collect_data_files("espeakng_loader")

a = Analysis(
    ["../service/__main__.py"],
    pathex=[".."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ORION",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # no black console window; logs go to %LOCALAPPDATA%\ORION\logs
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ORION")
