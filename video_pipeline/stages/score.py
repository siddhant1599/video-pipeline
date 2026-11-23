"""score: measure lip-sync of the finished shots with SyncNet (LatentSync's own evaluator).

Reports a confidence (higher is better; unsynced footage scores around 1-2,
well-synced speech 7 and up) and the audio/video offset in frames (0 is on the
beat). Scores are comparable between versions of the same shot, not between
different shots. A shot needs at least 2 seconds of visible face.
Writes `work/lipsync/scores.json`.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

from ..config import Project
from ..envs import latentsync_dir
from ..util import ffmpeg, log

FPS = 25


def main(args):
    pr = Project(args.project)
    ls = latentsync_dir()
    out_file = pr.work / "lipsync" / "scores.json"
    scores = json.loads(out_file.read_text()) if out_file.exists() else {}
    for shot in pr.select(args.shot, "lipsync"):
        sid = shot["id"]
        video = pr.shot_video(sid)
        src = ["-i", video] if video.exists() else ["-framerate", pr.fps, "-i", pr.latest_frames(sid) / "%05d.png"]
        what = "finished shot" if video.exists() else "frames before enhance"
        n = pr.shot_frames(sid)
        first, last = (shot["lipsync"] if isinstance(shot["lipsync"], dict) else {}).get("range", [0, n])
        t0 = pr.shot_start(sid) + first / pr.fps
        clip = pr.work / "lipsync" / sid / "score.mp4"
        clip.parent.mkdir(parents=True, exist_ok=True)
        # same 1:1 frame mapping as the lipsync stage: frames tagged 25 fps, audio stretched to match
        vf = f"trim=start_frame={first}:end_frame={last},setpts=N/{FPS}/TB"
        ffmpeg(*src, "-ss", f"{t0:.4f}", "-t", f"{(last - first) / pr.fps:.4f}", "-i", pr.audio_dir / "voice_only.wav",
               "-vf", vf, "-r", FPS, "-af", f"atempo={FPS / pr.fps:.6f}", "-c:v", "libx264", "-crf", 12, "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-ar", 16000, "-shortest", clip)
        r = subprocess.run([sys.executable, "-m", "eval.eval_sync_conf", "--video_path", str(clip), "--temp_dir", "temp_eval"],
                           cwd=ls, capture_output=True, text=True, env={**__import__("os").environ, "PYTHONPATH": str(ls)})
        text = r.stdout + r.stderr
        conf = re.search(r"confidence[^\d-]*(-?[\d.]+)", text, re.I)
        off = re.search(r"offset[^\d-]*(-?\d+)", text, re.I)
        if not conf:
            log(f"{sid}: SyncNet gave no score (needs 2 s of visible face). Last output:\n{text[-600:]}")
            continue
        scores[sid] = {"confidence": float(conf.group(1)), "offset_frames": int(off.group(1)) if off else None, "measured_on": what}
        log(f"{sid}: {scores[sid]}")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(scores, indent=1))
