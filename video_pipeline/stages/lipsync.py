"""lipsync: re-animate the mouth of a shot to the voice track with LatentSync.

For every shot with a `lipsync:` block the stage takes the shot's frames and the
stretch of `work/audio/voice_only.wav` that plays under it on the timeline.

LatentSync works at 25 fps in groups of 16 frames. To keep every frame of the
shot 1:1, the frames are tagged as 25 fps (not resampled), the audio is
time-stretched by 25/fps to stay in step, and the clip is padded to a whole
number of groups; the padding is dropped afterwards. Long shots are split into
overlapping segments that are cross-faded where they meet.

Shot options (`lipsync:`): `guidance` (default 2.0; 1.0 follows the audio less
closely), `steps` (20), `seed`, `range: [first, last)` frames to re-sync (the
face must be visible in all of them), `max_frames` per segment (160),
`backend: local | hosted`.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..config import FRAME_PATTERN, Project
from ..envs import REPO, latentsync_dir
from ..util import done, ffmpeg, frame_files, fresh_dir, frame_path, log

GROUP, FPS = 16, 25


def segments(n: int, max_frames: int, overlap: int = GROUP) -> list[tuple[int, int]]:
    """[first, last) ranges covering n frames, each at most max_frames, neighbours sharing `overlap` frames."""
    max_frames = max(2 * GROUP, max_frames - max_frames % GROUP)
    if n <= max_frames:
        return [(0, n)]
    out, a = [], 0
    while True:
        b = min(a + max_frames, n)
        out.append((a, b))
        if b == n:
            return out
        a = b - overlap


def build_inputs(pr: Project, frames: list[Path], t0: float, tmp: Path) -> tuple[Path, Path, int]:
    """25 fps clip (padded to a multiple of 16 frames) and the matching 16 kHz audio."""
    n = len(frames)
    padded = -(-n // GROUP) * GROUP
    fdir = fresh_dir(tmp / "in")
    for i in range(padded):
        shutil.copy(frames[min(i, n - 1)], frame_path(fdir, i))
    video, audio = tmp / "in.mp4", tmp / "in.wav"
    ffmpeg("-framerate", FPS, "-i", fdir / FRAME_PATTERN, "-c:v", "libx264", "-crf", 8, "-pix_fmt", "yuv420p", video)
    tempo = FPS / pr.fps
    ffmpeg("-ss", f"{t0:.4f}", "-t", f"{n / pr.fps:.4f}", "-i", pr.audio_dir / "voice_only.wav",
           "-af", f"atempo={tempo:.6f},apad=pad_dur={(padded - n) / FPS + 0.4:.3f}", "-ar", 16000, "-ac", 1, audio)
    shutil.rmtree(fdir)
    return video, audio, padded


def run_local(video: Path, audio: Path, out: Path, opt: dict):
    ls = latentsync_dir()
    if not (ls / "checkpoints" / "latentsync_unet.pt").exists():
        raise SystemExit(f"[video-pipeline] error: LatentSync is not set up at {ls}; run scripts/setup_lipsync.sh")
    runner = REPO / "video_pipeline" / "vendor" / "latentsync_runner.py"
    subprocess.run([sys.executable, str(runner), str(video), str(audio), str(out), str(int(opt.get("steps", 20))),
                    str(float(opt.get("guidance", 2.0))), str(int(opt.get("seed", 1247)))], cwd=ls, check=True)


def run_hosted(video: Path, audio: Path, out: Path, opt: dict):
    """A hosted LatentSync Space. Quota-limited and lower bitrate than the local run; token from HF_TOKEN only."""
    from gradio_client import Client, handle_file

    c = Client(opt.get("space", "fffiloni/LatentSync"), token=os.environ.get("HF_TOKEN") or None, verbose=False)
    r = c.predict(input_video_path=handle_file(str(video)), input_audio_path=handle_file(str(audio)),
                  api_name=opt.get("api_name", "/generate_lip_sync_video"))
    p = r["video"] if isinstance(r, dict) else r
    fresh_dir(out)
    ffmpeg("-i", p, "-start_number", 0, out / FRAME_PATTERN)


def main(args):
    import cv2
    import numpy as np

    pr = Project(args.project)
    if not (pr.audio_dir / "voice_only.wav").exists() and pr.select(args.shot, "lipsync"):
        raise SystemExit("[video-pipeline] error: work/audio/voice_only.wav is missing; run `video-pipeline mix` first")
    for shot in pr.select(args.shot, "lipsync"):
        sid, opt = shot["id"], shot["lipsync"] if isinstance(shot["lipsync"], dict) else {}
        out = pr.frames_dir(sid, "lipsync")
        if done(out, args.force):
            continue
        base = frame_files(pr.latest_frames(sid, before="lipsync"))
        first, last = opt.get("range", [0, len(base)])
        last = min(int(last), len(base))
        t_shot = pr.shot_start(sid)
        tmp = pr.work / "lipsync" / sid
        tmp.mkdir(parents=True, exist_ok=True)
        segs = segments(last - first, int(opt.get("max_frames", 160)))
        results = []
        for k, (a, b) in enumerate(segs):
            seg_out = tmp / f"seg{k}"
            if not (seg_out.is_dir() and len(frame_files(seg_out)) >= b - a) or args.force:
                video, audio, _ = build_inputs(pr, base[first + a: first + b], t_shot + (first + a) / pr.fps, tmp)
                log(f"{sid}: segment {k + 1}/{len(segs)}, frames [{first + a}, {first + b})")
                fresh_dir(seg_out)
                (run_hosted if opt.get("backend") == "hosted" else run_local)(video, audio, seg_out, opt)
            results.append(frame_files(seg_out))
        fresh_dir(out)
        fade = int(opt.get("crossfade", 3))
        for i, f in enumerate(base):
            j = i - first
            dst = out / f.name
            if j < 0 or i >= last:
                shutil.copy(f, dst)
                continue
            owners = [k for k, (a, b) in enumerate(segs) if a <= j < b]
            if len(owners) == 1:
                shutil.copy(results[owners[0]][j - segs[owners[0]][0]], dst)
                continue
            # inside an overlap: switch from the earlier to the later segment with a short cross-fade at its middle
            k0, k1 = owners[0], owners[1]
            mid = (segs[k1][0] + segs[k0][1]) / 2
            w = float(np.clip((j - mid) / fade + 0.5, 0, 1))
            f0, f1 = results[k0][j - segs[k0][0]], results[k1][j - segs[k1][0]]
            if w in (0.0, 1.0):
                shutil.copy(f1 if w else f0, dst)
            else:
                x = cv2.imread(str(f0)).astype(np.float32) * (1 - w) + cv2.imread(str(f1)).astype(np.float32) * w
                cv2.imwrite(str(dst), x.round().astype(np.uint8))
        log(f"{sid}: lip-synced frames [{first}, {last}) in {len(segs)} segment(s) -> {out}")
