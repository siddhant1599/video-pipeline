"""Command line: `video-pipeline <stage> -p <project.yaml>`; see `video-pipeline --help`."""
from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys

from . import __version__
from .envs import ORDER, REPO, STAGES, python_for, same_interpreter

HELP = {
    "init": "create a new project folder with a starter project.yaml",
    "status": "show the timeline and what each stage has produced so far",
    "doctor": "check that ffmpeg, the environments, the models and HyperFrames are in place",
    "run": "run several stages in order (--from / --to)",
    "ingest": "cut shots out of the source videos, build still-image shots, split speech from music",
    "clean": "remove baked-in text (captions, labels) from shot frames",
    "generate": "make new shots from a start image and a prompt (Wan 2.2 image-to-video)",
    "smooth": "even out stuttering motion and retime a shot (optical flow + RIFE)",
    "voice": "record the spoken lines in the reference voice (Chatterbox), pick the best take",
    "mix": "build the soundtrack: voice lines, music bed, effects",
    "transcribe": "word timings of the voice track, for captions",
    "lipsync": "re-animate the mouth to the voice track (LatentSync)",
    "enhance": "upscale each shot to the output size, optional face restoration",
    "score": "measure lip-sync quality of the finished shots (SyncNet)",
    "compose": "write the HyperFrames project: cut, captions, overlays, end card",
    "render": "lint, check, snapshot and render the film with HyperFrames",
}


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="video-pipeline", description="Config-driven pipeline for short talking-head videos (ads, explainers, promos).")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="<command>")
    for name, text in HELP.items():
        sp = sub.add_parser(name, help=text, description=text)
        if name == "init":
            sp.add_argument("dir", help="folder to create")
            continue
        if name == "doctor":
            continue
        sp.add_argument("-p", "--project", default=".", help="project.yaml or the folder holding it (default: current folder)")
        if name == "status":
            continue
        sp.add_argument("--shot", action="append", help="only this shot (repeatable)")
        sp.add_argument("--line", action="append", help="only this voice line (repeatable; voice stage)")
        sp.add_argument("--force", action="store_true", help="redo work whose output already exists")
        if name == "run":
            sp.add_argument("--from", dest="first", default=ORDER[0], choices=ORDER)
            sp.add_argument("--to", dest="last", default=ORDER[-1], choices=ORDER)
        if name == "render":
            sp.add_argument("--no-render", action="store_true", help="stop after lint, check and snapshots")
            sp.add_argument("--at", help="comma-separated seconds to snapshot (default: middle of every caption)")
    return ap


def stage_argv(args) -> list[str]:
    argv = ["-p", args.project]
    for s in args.shot or []:
        argv += ["--shot", s]
    for l in args.line or []:
        argv += ["--line", l]
    if args.force:
        argv.append("--force")
    if getattr(args, "no_render", False):
        argv.append("--no-render")
    if getattr(args, "at", None):
        argv += ["--at", args.at]
    return argv


def run_stage(stage: str, args) -> int:
    env = STAGES[stage]
    py = python_for(env)
    if py is None:
        print(f"[video-pipeline] error: the '{env}' environment is missing; run scripts/setup_{env}.sh "
              f"(or point VIDEO_PIPELINE_PY_{env.upper()} at a Python that has it)", file=sys.stderr)
        return 2
    if same_interpreter(py):
        mod = importlib.import_module(f"video_pipeline.stages.{stage}")
        return int(mod.main(args) or 0)
    envv = dict(os.environ, VIDEO_PIPELINE_IN_STAGE="1", PYTHONPATH=f"{REPO}{os.pathsep}{os.environ.get('PYTHONPATH', '')}")
    return subprocess.call([str(py), "-m", "video_pipeline.cli", stage, *stage_argv(args)], env=envv)


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    from .config import ConfigError
    try:
        if args.cmd in ("init", "status", "doctor"):
            return int(importlib.import_module(f"video_pipeline.stages.{args.cmd}").main(args) or 0)
        if args.cmd == "run":
            for stage in ORDER[ORDER.index(args.first): ORDER.index(args.last) + 1]:
                print(f"[video-pipeline] ===== {stage} =====", flush=True)
                rc = run_stage(stage, args)
                if rc:
                    return rc
            return 0
        return run_stage(args.cmd, args)
    except ConfigError as e:
        print(f"[video-pipeline] config error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
