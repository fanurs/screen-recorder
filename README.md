# screen-recorder

A Windows GUI screen recorder built in Python.

- Capture a **full monitor**, a **single window**, or an **arbitrary rectangular region**.
- Downscale output to a target height (**480p–1080p**, default 720p), aspect-preserving.
- Adjustable frame rate (**10–60 Hz**, default 30).
- Visually-lossless **H.264** (libx264, optional NVENC) into an `.mkv`.
- Live **estimated bitrate / file size** before you hit record.

## Setup

```powershell
uv sync
uv run screen-recorder
```

FFmpeg ships bundled via `imageio-ffmpeg` — no system install needed.
