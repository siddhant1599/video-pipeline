"""ingest: turn the inputs into per-shot frame folders and separated audio stems.

- `from:` shots are cut out of a source video at the project frame rate.
- `image:` shots become a run of frames from a still, with an optional slow push-in.
- sources with `separate: true` are split into speech (`vocals.wav`) and the rest
  (`no_vocals.wav`) with Demucs, so original speech can be reused without its music.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys

from ..config import FRAME_PATTERN, Project
from ..util import done, ffmpeg, frame_files, fresh_dir, frame_path, log, probe


def cut_shot(pr: Project, shot: dict, force: bool):
    out = pr.frames_dir(shot["id"], "raw")
    if done(out, force):
        return
    spec = shot["from"]
    src = pr.source_path(spec["source"])
    fresh_dir(out)
    if spec.get("keep_fps"):
        # keep the clip's own frames (e.g. a 16 fps generated clip); `smooth` retimes them to the project frame rate
        num, den = probe(src, "stream=r_frame_rate")[0].split("/")
        src_fps = float(num) / float(den)
        if "start_frame" in spec or "end_frame" in spec:
            a, b = int(spec.get("start_frame", 0)), int(spec.get("end_frame", 10 ** 9))
        else:
            a = int(round(float(spec.get("start", 0)) * src_fps))
            b = int(round(float(spec["end"]) * src_fps)) if "end" in spec else 10 ** 9
        vf = f"trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS"
        meta = pr.work / "generated" / f"{shot['id']}.json"
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(json.dumps({"fps": src_fps, "source": spec["source"]}))
    else:
        a, b = pr.frame_range(spec)
        vf = f"fps={pr.fps:g},trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS"
    if spec.get("crop"):
        x, y, w, h = spec["crop"]
        vf += f",crop={w}:{h}:{x}:{y}"
    ffmpeg("-i", src, "-vf", vf, "-vsync", "passthrough", "-start_number", 0, out / FRAME_PATTERN)
    log(f"{shot['id']}: {len(frame_files(out))} frames from '{spec['source']}'")


def still_shot(pr: Project, shot: dict, force: bool):
    import cv2

    out = pr.frames_dir(shot["id"], "raw")
    if done(out, force):
        return
    spec = shot["image"] if isinstance(shot["image"], dict) else {"path": shot["image"]}
    img = cv2.imread(str(pr.path(spec["path"])))
    if img is None:
        raise SystemExit(f"[video-pipeline] error: cannot read image {pr.path(spec['path'])}")
    n = pr.declared_frames(shot["id"])
    z0, z1 = spec.get("zoom", [1.0, 1.0])
    cx, cy = spec.get("center", [0.5, 0.5])
    h, w = img.shape[:2]
    fresh_dir(out)
    for i in range(n):
        z = z0 + (z1 - z0) * (i / max(1, n - 1))
        cw, ch = w / z, h / z
        x0 = min(max(cx * w - cw / 2, 0), w - cw)
        y0 = min(max(cy * h - ch / 2, 0), h - ch)
        # sub-pixel crop so a slow push-in does not step from frame to frame
        m = [[z, 0, -x0 * z], [0, z, -y0 * z]]
        import numpy as np

        cv2.imwrite(str(frame_path(out, i)), cv2.warpAffine(img, np.float32(m), (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE))
    log(f"{shot['id']}: {n} frames from still, zoom {z0}->{z1}")


def separate(pr: Project, sid: str, force: bool):
    out = pr.stem(sid, "vocals")
    if done(out, force):
        return
    tmp = pr.work / "stems" / sid / "_demucs"
    wav = pr.work / "stems" / sid / "full.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg("-i", pr.source_path(sid), "-vn", "-ac", 2, "-ar", 44100, wav)
    subprocess.run([sys.executable, "-m", "demucs", "--two-stems", "vocals", "-n", "htdemucs", "-o", str(tmp), str(wav)], check=True)
    for stem in ("vocals", "no_vocals"):
        shutil.move(str(tmp / "htdemucs" / "full" / f"{stem}.wav"), str(pr.stem(sid, stem)))
    shutil.rmtree(tmp, ignore_errors=True)
    log(f"source '{sid}': speech and music separated -> {out.parent}")


def main(args):
    pr = Project(args.project)
    for shot in pr.select(args.shot):
        if "from" in shot:
            cut_shot(pr, shot, args.force)
        elif "image" in shot:
            still_shot(pr, shot, args.force)
    for sid, src in pr.sources.items():
        if isinstance(src, dict) and src.get("separate"):
            separate(pr, sid, args.force and not args.shot)  # --shot --force redoes that shot only
