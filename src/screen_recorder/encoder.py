"""FFmpeg-backed H.264 encoder.

Frames are written as raw BGR bytes to FFmpeg's stdin and encoded into an MKV
intermediate (crash-safe); :func:`remux_to_mp4` later rewraps the stream into the
final container losslessly. FFmpeg ships bundled via ``imageio-ffmpeg`` so no
system install is required. Two codecs are supported: software ``libx264``
(always available) and ``h264_nvenc`` (NVIDIA GPUs only, auto-probed).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

import imageio_ffmpeg

# Suppress the console window FFmpeg would otherwise pop up on Windows.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_nvenc_cache: bool | None = None


def ffmpeg_exe() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _nvenc_compiled_in() -> bool:
    """Whether the bundled FFmpeg lists the ``h264_nvenc`` encoder (cached).

    This only proves the encoder is compiled in, not that a working GPU/driver
    is present — :func:`nvenc_usable` confirms it can actually encode.
    """
    global _nvenc_cache
    if _nvenc_cache is not None:
        return _nvenc_cache
    try:
        out = subprocess.run(
            [ffmpeg_exe(), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=_NO_WINDOW,
        )
        _nvenc_cache = "h264_nvenc" in out.stdout
    except Exception:
        _nvenc_cache = False
    return _nvenc_cache


def nvenc_usable() -> bool:
    """Actually try to encode one frame with NVENC to prove the GPU works.

    Generates a tiny test pattern entirely inside FFmpeg (no input piping) and
    encodes it to nul. Returns False on any failure: no NVIDIA GPU, outdated
    driver, or a session limit. This is the real runtime check before recording.
    """
    if not _nvenc_compiled_in():
        return False
    try:
        proc = subprocess.run(
            [
                ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black:s=128x128:r=30:d=0.1",
                "-c:v", "h264_nvenc", "-f", "null", "-",
            ],
            capture_output=True,
            timeout=20,
            creationflags=_NO_WINDOW,
        )
        return proc.returncode == 0
    except Exception:
        return False


@dataclass
class EncoderConfig:
    width: int
    height: int
    fps: int
    crf: int                 # quality: lower = better/larger (visually lossless ~ 12-18)
    output_path: str
    use_nvenc: bool = False


class FfmpegEncoder:
    """Spawns FFmpeg and accepts raw BGR frames via :meth:`write`."""

    def __init__(self, cfg: EncoderConfig) -> None:
        self.cfg = cfg
        self._proc: subprocess.Popen | None = None

    def _build_args(self) -> list[str]:
        c = self.cfg
        args = [
            ffmpeg_exe(),
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{c.width}x{c.height}",
            "-r", str(c.fps),
            "-i", "-",
        ]
        if c.use_nvenc:
            args += [
                "-c:v", "h264_nvenc",
                "-preset", "p5",
                "-rc", "constqp",
                "-qp", str(c.crf),
                "-pix_fmt", "yuv420p",
            ]
        else:
            args += [
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", str(c.crf),
                "-pix_fmt", "yuv420p",
            ]
        args.append(c.output_path)
        return args

    def start(self) -> None:
        self._proc = subprocess.Popen(
            self._build_args(),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=_NO_WINDOW,
        )

    def write(self, frame_bgr_bytes: bytes) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError("encoder not started")
        self._proc.stdin.write(frame_bgr_bytes)

    def close(self) -> str | None:
        """Flush and wait for FFmpeg to finish. Returns stderr text on error."""
        if self._proc is None:
            return None
        proc, self._proc = self._proc, None
        try:
            if proc.stdin:
                proc.stdin.close()
        except BrokenPipeError:
            pass
        _, stderr = proc.communicate()
        if proc.returncode not in (0, None):
            return (stderr or b"").decode(errors="replace")
        return None


def remux_to_mp4(src_mkv: str, dst_mp4: str) -> str | None:
    """Copy the H.264 stream from an MKV into an MP4 with no re-encode.

    ``-c copy`` rewraps the exact same compressed bytes, so it is lossless and
    near-instant. Returns FFmpeg's error text on failure, else None.
    """
    try:
        proc = subprocess.run(
            [
                ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
                "-i", src_mkv,
                "-c", "copy",
                "-movflags", "+faststart",
                dst_mp4,
            ],
            capture_output=True,
            timeout=120,
            creationflags=_NO_WINDOW,
        )
        if proc.returncode != 0:
            return (proc.stderr or b"").decode(errors="replace")
        return None
    except Exception as exc:  # noqa: BLE001
        return str(exc)
