"""enhance: bring every shot to the output size and write it as a video.

Each frame is centre-cropped to the output aspect ratio, upscaled 4x with
Real-ESRGAN (the compact `realesr-general-x4v3` model) and reduced to the
output size, which sharpens low-resolution and generated footage. With
`enhance: {face: 0.6}` the face is additionally restored with GFPGAN and
blended in at that weight (0 = off; high values look waxy). `upscale: false`
only resizes. Runs in several worker processes.
"""
from __future__ import annotations

import os
from multiprocessing import Process

import cv2

from ..config import Project
from ..envs import models_dir
from ..util import done, frame_files, fresh_dir, frames_to_video, log

_sr = None
_face = None


def need(name: str):
    p = models_dir() / name
    if not p.exists():
        raise SystemExit(f"[video-pipeline] error: model {p} is missing; run scripts/download_models.sh")
    return str(p)


def fit(img, w: int, h: int):
    """Centre-crop to the w:h aspect ratio."""
    H, W = img.shape[:2]
    if W / H > w / h + 0.005:
        nw = int(round(H * w / h))
        x0 = (W - nw) // 2
        return img[:, x0:x0 + nw]
    if W / H < w / h - 0.005:
        nh = int(round(W * h / w))
        y0 = (H - nh) // 2
        return img[y0:y0 + nh]
    return img


def upscale(img, w: int, h: int):
    global _sr
    import torch
    from spandrel import ModelLoader

    if _sr is None:
        _sr = ModelLoader().load_from_file(need("realesr-general-x4v3.pth")).model.eval()
        if torch.cuda.is_available():
            _sr = _sr.cuda()
    dev = next(_sr.parameters()).device
    with torch.inference_mode():
        x = torch.from_numpy(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).permute(2, 0, 1).float().div(255)[None].to(dev)
        y = _sr(x).clamp(0, 1)[0].permute(1, 2, 0).mul(255).round().byte().cpu().numpy()
    return cv2.resize(cv2.cvtColor(y, cv2.COLOR_RGB2BGR), (w, h), interpolation=cv2.INTER_AREA)


def restore_face(img, weight: float):
    """GFPGAN on the main face, blended with the upscaled frame at `weight`."""
    global _face
    import torch
    from facexlib.utils.face_restoration_helper import FaceRestoreHelper
    from spandrel import ModelLoader

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if _face is None:
        gan = ModelLoader().load_from_file(need("GFPGANv1.4.pth")).model.eval().to(dev)
        helper = FaceRestoreHelper(1, face_size=512, crop_ratio=(1, 1), det_model="retinaface_resnet50", save_ext="png", use_parse=True, device=dev)
        _face = (gan, helper)
    gan, h = _face
    h.clean_all()
    h.read_image(img)
    h.get_face_landmarks_5(only_center_face=True, resize=640, eye_dist_threshold=5)
    h.align_warp_face()
    if not h.cropped_faces:
        return img
    with torch.inference_mode():
        for cf in h.cropped_faces:
            t = torch.from_numpy(cv2.cvtColor(cf, cv2.COLOR_BGR2RGB)).permute(2, 0, 1).float().div(255).sub(0.5).div(0.5)[None].to(dev)
            o = gan(t)
            o = o[0] if isinstance(o, (tuple, list)) else o
            o = o.squeeze(0).clamp(-1, 1).add(1).div(2).permute(1, 2, 0).mul(255).round().byte().cpu().numpy()
            h.add_restored_face(cv2.addWeighted(cv2.cvtColor(o, cv2.COLOR_RGB2BGR), weight, cf, 1 - weight, 0))
    h.get_inverse_affine(None)
    return h.paste_faces_to_input_image()


def work(files, k, workers, tmp, w, h, opt):
    import torch

    torch.set_num_threads(max(1, (os.cpu_count() or 4) // workers))
    face = float(opt.get("face", 0))
    for f in files[k::workers]:
        img = fit(cv2.imread(str(f)), w, h)
        if opt.get("crop"):
            x, y, cw, ch = opt["crop"]
            img = fit(img[y:y + ch, x:x + cw], w, h)
        if opt.get("upscale", True):
            img = upscale(img, w, h)
        else:
            img = cv2.resize(img, (w, h), interpolation=cv2.INTER_LANCZOS4)
        if face > 0:
            img = restore_face(img, face)
        cv2.imwrite(str(tmp / f.name), img)


def main(args):
    pr = Project(args.project)
    defaults = pr.cfg.get("enhance") or {}
    workers = int(defaults.get("workers", 4))
    for shot in pr.select(args.shot):
        sid = shot["id"]
        out = pr.shot_video(sid)
        if done(out, args.force):
            continue
        opt = {**defaults, **(shot.get("enhance") or {})}
        files = frame_files(pr.latest_frames(sid))
        tmp = fresh_dir(pr.work / "enhance" / sid)
        ps = [Process(target=work, args=(files, k, workers, tmp, pr.width, pr.height, opt)) for k in range(workers)]
        [p.start() for p in ps]
        [p.join() for p in ps]
        if any(p.exitcode for p in ps) or len(frame_files(tmp)) != len(files):
            raise SystemExit(f"[video-pipeline] error: enhance failed for shot '{sid}' ({len(frame_files(tmp))} of {len(files)} frames)")
        frames_to_video(tmp, out, f"{pr.fps:g}", int(defaults.get("crf", 13)))
        if not defaults.get("keep_frames"):
            import shutil

            shutil.rmtree(tmp)
        log(f"{sid}: {len(files)} frames at {pr.width}x{pr.height} -> {out}")
