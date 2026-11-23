"""doctor: check that the tools, environments and models are in place."""
from __future__ import annotations

import shutil
import subprocess

from ..envs import latentsync_dir, models_dir, python_for

CHECKS = {
    "core": ("yaml, soundfile, scipy, gradio_client, faster_whisper, demucs", "ingest, generate, mix, transcribe, compose, render"),
    "enhance": ("cv2, torch, spandrel, facexlib, ccvfi, simple_lama_inpainting", "clean, smooth, enhance"),
    "voice": ("chatterbox, librosa, soundfile", "voice"),
    "lipsync": ("torch, diffusers, omegaconf, face_alignment, cv2", "lipsync, score"),
}


def main(args):
    ok = True

    def line(good, what, hint=""):
        nonlocal ok
        ok &= bool(good) or hint.startswith("optional")
        print(f"  [{'ok' if good else '--'}] {what}" + (f"  ({hint})" if hint and not good else ""))

    print("system")
    for tool in ("ffmpeg", "ffprobe"):
        line(shutil.which(tool), tool, "install FFmpeg 4.4 or newer")
    hf = shutil.which("hyperframes") or shutil.which("npx")
    line(hf, "HyperFrames (hyperframes or npx)", "install Node.js 22+; see scripts/setup_hyperframes.sh")
    print("environments")
    for env, (mods, stages) in CHECKS.items():
        py = python_for(env)
        if not py:
            line(False, f"{env}: {stages}", f"run scripts/setup_{env}.sh")
            continue
        r = subprocess.run([str(py), "-c", f"import {mods}"], capture_output=True, text=True)
        line(r.returncode == 0, f"{env}: {stages}", (r.stderr.strip().splitlines() or ["import failed"])[-1])
    print("models")
    m = models_dir()
    line((m / "realesr-general-x4v3.pth").exists(), "Real-ESRGAN upscaler", "run scripts/download_models.sh")
    line((m / "GFPGANv1.4.pth").exists(), "GFPGAN face restoration", "optional; run scripts/download_models.sh")
    ls = latentsync_dir()
    line((ls / "checkpoints" / "latentsync_unet.pt").exists(), f"LatentSync at {ls}", "run scripts/setup_lipsync.sh")
    line((ls / "checkpoints" / "auxiliary" / "syncnet_v2.model").exists(), "SyncNet scorer", "optional; run scripts/setup_lipsync.sh")
    import os
    print("hosted services")
    line(os.environ.get("HF_TOKEN"), "HF_TOKEN is set", "optional; only `generate` and the hosted lipsync backend use it")
    return 0 if ok else 1
