"""generate: make a new shot from a start image and a prompt.

Uses a hosted Wan 2.2 image-to-video Space through `gradio_client`. Hosted
Spaces change and have quotas: the Space id, endpoint and parameters are all
configurable under `generate:` in the project file, and the Hugging Face token
is read from the HF_TOKEN environment variable only (never from a file).
"""
from __future__ import annotations

import json
import os
import shutil

from ..config import FRAME_PATTERN, Project
from ..util import done, ffmpeg, frame_files, fresh_dir, log, probe

DEFAULTS = {
    "space": "Upsampler/wan-2-2-14b-image-to-video",
    "api_name": "/generate_video",
    "steps": 6,
    "guidance_scale": 1,
    "guidance_scale_2": 1,
    "seed": 42,
    "seconds": 5,
}


def image_of(pr: Project, ref):
    """A path, or {shot: id, frame: n} to take a frame (negative counts from the end) of another shot."""
    if isinstance(ref, dict):
        files = frame_files(pr.latest_frames(ref["shot"]))
        return files[int(ref.get("frame", -1))]
    return pr.path(ref)


def main(args):
    pr = Project(args.project)
    shots = pr.select(args.shot, "generate")
    if not shots:
        return
    from gradio_client import Client, handle_file

    token = os.environ.get("HF_TOKEN") or None
    if not token:
        log("HF_TOKEN is not set: calling the Space anonymously (very small quota)")
    opts = {**DEFAULTS, **(pr.cfg.get("generate") or {})}
    for shot in shots:
        out = pr.frames_dir(shot["id"], "raw")
        if done(out, args.force):
            continue
        g = {**opts, **shot["generate"]}
        client = Client(g["space"], verbose=False, token=token)
        end = g.get("end_image")
        r = client.predict(
            input_image=handle_file(str(image_of(pr, g["image"]))), prompt=g["prompt"], steps=g["steps"],
            duration_seconds=float(g["seconds"]), guidance_scale=g["guidance_scale"], guidance_scale_2=g["guidance_scale_2"],
            seed=int(g["seed"]), randomize_seed=False, end_image=handle_file(str(image_of(pr, end))) if end else None,
            api_name=g["api_name"],
        )
        v = r[0] if isinstance(r, (list, tuple)) else r
        v = v.get("video", v) if isinstance(v, dict) else v
        clip = pr.work / "generated" / f"{shot['id']}.mp4"
        clip.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(v, clip)
        fresh_dir(out)
        # keep the generator's own frames (no fps conversion): `smooth` retimes them to the project frame rate
        ffmpeg("-i", clip, "-start_number", 0, out / FRAME_PATTERN)
        num, den = probe(clip, "stream=r_frame_rate")[0].split("/")
        (clip.with_suffix(".json")).write_text(json.dumps({"fps": float(num) / float(den), "prompt": g["prompt"], "seed": int(g["seed"])}))
        log(f"{shot['id']}: generated {len(frame_files(out))} frames -> {out}")
