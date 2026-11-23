"""render: check the HyperFrames project and render the film.

Runs, in order: `hyperframes lint`, `hyperframes check`, `hyperframes snapshot`
(still frames to look at before spending time on a render; default: the middle
of every caption and of every shot) and `hyperframes render`. Lint errors stop
the run; `--no-render` stops after the snapshots.

The HyperFrames command is `$VIDEO_PIPELINE_HYPERFRAMES`, else `hyperframes` on PATH,
else `npx --yes hyperframes@<project.hyperframes_version>`.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess

from ..config import Project
from ..util import ffmpeg, log


def hyperframes(pr: Project) -> list[str]:
    if os.environ.get("VIDEO_PIPELINE_HYPERFRAMES"):
        return shlex.split(os.environ["VIDEO_PIPELINE_HYPERFRAMES"])
    if shutil.which("hyperframes"):
        return ["hyperframes"]
    if shutil.which("npx"):
        return ["npx", "--yes", f"hyperframes@{(pr.cfg.get('project') or {}).get('hyperframes_version', '0.9.70')}"]
    raise SystemExit("[video-pipeline] error: HyperFrames not found; install Node.js 22+ (see scripts/setup_hyperframes.sh)")


def main(args):
    pr = Project(args.project)
    if not (pr.hf / "index.html").exists():
        raise SystemExit("[video-pipeline] error: no HyperFrames project yet; run `video-pipeline compose`")
    hf = hyperframes(pr)
    opt = pr.cfg.get("render") or {}

    def step(name: str, *a, fatal: bool = True) -> int:
        log(f"hyperframes {name} {' '.join(str(x) for x in a)}")
        rc = subprocess.call([*hf, name, *[str(x) for x in a]], cwd=pr.hf)
        if rc and fatal:
            raise SystemExit(f"[video-pipeline] error: hyperframes {name} failed ({rc})")
        return rc

    step("lint")
    if step("check", fatal=False):
        log("check reported problems: read them above; warnings about caption hold time are advice, errors need fixing")
        if opt.get("strict", False):
            raise SystemExit(1)
    if getattr(args, "at", None):
        times = args.at
    else:
        tl = json.loads((pr.hf / "timeline.json").read_text())
        ts = sorted({round(c["start"] + (c["end"] - c["start"]) / 2, 2) for c in tl["captions"]} |
                    {round(s["start"] + s["duration"] / 2, 2) for s in tl["shots"]} | {round(tl["duration"] - 0.5, 2)})
        times = ",".join(str(t) for t in ts)
    step("snapshot", "--at", times, "--no-end", "--output", "snapshots", fatal=False)
    log(f"snapshots: {pr.hf / 'snapshots'} - look at them before trusting the render")
    if getattr(args, "no_render", False):
        return 0
    pr.out.mkdir(parents=True, exist_ok=True)
    master = pr.out / f"{pr.name}.mp4"
    step("render", "--fps", f"{pr.fps:g}", "--crf", opt.get("crf", 12), "-o", master)
    if opt.get("share_crf"):
        share = pr.out / f"{pr.name}-share.mp4"
        ffmpeg("-i", master, "-c:v", "libx264", "-crf", opt["share_crf"], "-preset", "slow", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", share)
        log(f"share copy -> {share}")
    log(f"film -> {master}")
