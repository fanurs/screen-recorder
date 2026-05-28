# PyInstaller spec for the screen recorder.
#
# Build with:   uv run pyinstaller screen-recorder.spec
# Result:       dist/ScreenRecorder/ScreenRecorder.exe  (windowed, with icon, bundles FFmpeg)
#
# Why a .spec rather than command-line flags?
# - We need to bundle two non-Python files:
#   (1) the FFmpeg binary that imageio-ffmpeg ships, and
#   (2) our app.ico (used for the in-app window/taskbar icon at runtime).
# - We want a windowed onedir build (no console box, fast startup, no temp unpack).

from pathlib import Path

import imageio_ffmpeg

PROJECT_ROOT = Path(SPECPATH).resolve()
ICON_PATH = PROJECT_ROOT / "src" / "screen_recorder" / "assets" / "app.ico"
FFMPEG_EXE = Path(imageio_ffmpeg.get_ffmpeg_exe())

a = Analysis(
    [str(PROJECT_ROOT / "src" / "screen_recorder" / "__main__.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[
        # Drop ffmpeg.exe under the same relative location our code expects
        # (imageio_ffmpeg/binaries/...), so imageio_ffmpeg.get_ffmpeg_exe()
        # keeps working inside the frozen app.
        (str(FFMPEG_EXE), "imageio_ffmpeg/binaries"),
    ],
    datas=[
        (str(ICON_PATH), "screen_recorder/assets"),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Trim large optional Qt modules we don't use.
        "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ScreenRecorder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # windowed app: no terminal box
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_PATH),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ScreenRecorder",
)
