# screen-recorder

A Windows GUI screen recorder built in Python.

- Capture a **full monitor**, a **single window**, or an **arbitrary rectangular region**.
- Downscale output to a target height (**480p–1080p**, default 720p), aspect-preserving.
- Adjustable frame rate (**10–60 Hz**, default 30).
- Visually-lossless **H.264** (libx264, optional NVENC), with automatic GPU→CPU fallback.
- Output to **MP4** (via crash-safe MKV intermediate, lossless remux), or MKV directly.
- Live **estimated bitrate / file size** before you hit record.
- Remembers your last-used settings.

## Run from source (development)

```powershell
uv sync
uv run screen-recorder
```

FFmpeg ships bundled via `imageio-ffmpeg` — no system install needed.

## Install as a Windows app

Build a self-contained `.exe` (with bundled FFmpeg + icon, no console window), then add a Start-menu shortcut:

```powershell
uv sync                                          # install build deps
uv run pyinstaller screen-recorder.spec          # produces dist/ScreenRecorder/
tools/install_shortcut.ps1                       # adds a Start-menu shortcut
```

After this, press **Win** and type *Screen Recorder*.

## Where things live (per Windows conventions)

- App settings: `%APPDATA%\ScreenRecorder\config.json` — written on app close, read on launch.
- Default recording folder: `%USERPROFILE%\Videos\ScreenRecorder\`, with timestamped filenames (`recording-YYYY-MM-DD_HH-MM-SS.mp4`). You can override per-recording with the **Save to…** button.

## Tests

```powershell
uv run pytest                 # all tests
uv run pytest -m "not e2e"    # fast tests only (no real recording)
```
