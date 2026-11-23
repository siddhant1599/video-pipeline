"""Small helpers shared by the stages: ffmpeg, frame folders, logging."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .config import FRAME_PATTERN


def log(*a):
    print("[video-pipeline]", *a, flush=True)


def die(msg: str, code: int = 1):
    print(f"[video-pipeline] error: {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    cmd = [str(c) for c in cmd]
    return subprocess.run(cmd, check=True, **kw)


def ffmpeg(*args):
    run(["ffmpeg", "-v", "error", "-y", "-nostdin", *args])


def probe(path, entries: str, stream: str = "v:0") -> list[str]:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", entries, "-of", "csv=p=0", str(path)], text=True
    )
    return [x for x in out.strip().replace("\n", ",").split(",") if x]


def frame_files(d: Path) -> list[Path]:
    return sorted(Path(d).glob("*.png"))


def fresh_dir(d: Path) -> Path:
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    return d


def frame_path(d: Path, i: int) -> Path:
    return Path(d) / (FRAME_PATTERN % i)


def frames_to_video(d: Path, out: Path, fps, crf: int = 13, gop: int = 12, extra: list | None = None):
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg("-framerate", fps, "-i", Path(d) / FRAME_PATTERN, *(extra or []), "-c:v", "libx264", "-crf", crf, "-preset", "slow",
           "-pix_fmt", "yuv420p", "-g", gop, "-an", "-movflags", "+faststart", out)


def done(path: Path, force: bool) -> bool:
    """True when `path` already exists and --force was not given (the stage then skips it)."""
    path = Path(path)
    ok = path.exists() and (not path.is_dir() or any(path.iterdir()))
    if ok and not force:
        log(f"skip (exists, use --force to redo): {path}")
        return True
    return False
