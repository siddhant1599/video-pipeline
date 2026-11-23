"""clean: remove baked-in text (captions, watermarks, labels) from shot frames.

Each rule names a frame range and one or more boxes. In `text` mode only the
bright text pixels inside the boxes are masked (white top-hat), in `box` mode
the whole box is. The masked pixels are refilled with LaMa inpainting and
blended back with a feathered edge, so the rest of the frame is untouched.
"""
from __future__ import annotations

import shutil

import cv2
import numpy as np

from ..config import Project
from ..util import done, frame_files, fresh_dir, log


def text_mask(img, boxes, threshold=16, min_value=120, grow=7, kernel=11, mode="text"):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    m = np.zeros_like(g)
    if mode == "box":
        for x0, y0, x1, y1 in boxes:
            m[y0:y1, x0:x1] = 255
        return m
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel, kernel))
    th = cv2.morphologyEx(g, cv2.MORPH_TOPHAT, k)
    for x0, y0, x1, y1 in boxes:
        m[y0:y1, x0:x1] = ((th[y0:y1, x0:x1] > threshold) & (g[y0:y1, x0:x1] > min_value)).astype(np.uint8) * 255
    return cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (grow, grow)))


_lama = None


def inpaint(img, mask):
    global _lama
    if mask.max() == 0:
        return img
    from PIL import Image
    from simple_lama_inpainting import SimpleLama

    if _lama is None:
        import torch

        if not torch.cuda.is_available():
            # the packaged model was saved on a GPU; without this it cannot be loaded on a CPU-only machine
            load = torch.jit.load
            torch.jit.load = lambda f, map_location=None, **kw: load(f, map_location="cpu", **kw)
        _lama = SimpleLama()
    r = _lama(Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)), Image.fromarray(mask))
    r = cv2.cvtColor(np.array(r), cv2.COLOR_RGB2BGR)[: img.shape[0], : img.shape[1]]
    a = cv2.GaussianBlur(cv2.dilate(mask, np.ones((5, 5), np.uint8)), (0, 0), 2).astype(np.float32)[..., None] / 255
    return (img * (1 - a) + r * a).astype(np.uint8)


def main(args):
    pr = Project(args.project)
    for shot in pr.select(args.shot, "clean"):
        out = pr.frames_dir(shot["id"], "clean")
        if done(out, args.force):
            continue
        src = frame_files(pr.frames_dir(shot["id"], "raw"))
        if not src:
            raise SystemExit(f"[video-pipeline] error: shot '{shot['id']}' has no raw frames; run `video-pipeline ingest` first")
        fresh_dir(out)
        changed = 0
        for i, f in enumerate(src):
            rules = [r for r in shot["clean"] if r.get("frames", [0, len(src)])[0] <= i < r.get("frames", [0, len(src)])[1]]
            if not rules:
                shutil.copy(f, out / f.name)
                continue
            img = cv2.imread(str(f))
            mask = np.zeros(img.shape[:2], np.uint8)
            for r in rules:
                opts = {k: r[k] for k in ("threshold", "min_value", "grow", "kernel", "mode") if k in r}
                mask |= text_mask(img, r["boxes"], **opts)
            cv2.imwrite(str(out / f.name), inpaint(img, mask))
            changed += 1
        log(f"{shot['id']}: cleaned {changed} of {len(src)} frames")
