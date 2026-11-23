"""smooth: fix stuttering motion and retime a shot.

Generated clips often move unevenly (a big step, a small step, a big step), which
plays as stutter and survives plain frame interpolation. This stage

1. measures the motion of every source frame interval (Farneback optical flow,
   75th percentile of the flow magnitude),
2. places the output frames so that motion per output frame is even
   (motion equalisation: equal steps along the smoothed cumulative motion), and
3. synthesises each output frame at its exact fractional source position with
   RIFE, so the shot can also be slowed down or brought to the project frame rate.

Shot options (`smooth:`): `frames` (output length), `speed` (1.0 = real time,
below 1 slows down), `equalize` (default true), `window` (smoothing, in source
frames), `offset` (start, in output frames), `source_fps` (default: the
generator's frame rate for generated shots, else the project frame rate).
"""
from __future__ import annotations

import json

import cv2
import numpy as np

from ..config import Project
from ..util import done, frame_files, fresh_dir, frame_path, log


def motion(frames: list, width: int = 480) -> np.ndarray:
    """Motion of each interval between consecutive frames (pixels at `width` wide, 75th percentile)."""
    def small(f):
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        return cv2.resize(g, (width, int(round(g.shape[0] * width / g.shape[1]))), interpolation=cv2.INTER_AREA)

    out, prev = [], small(frames[0])
    for f in frames[1:]:
        cur = small(f)
        fl = cv2.calcOpticalFlowFarneback(prev, cur, None, 0.5, 3, 21, 3, 5, 1.2, 0)
        out.append(float(np.percentile(np.linalg.norm(fl, axis=2), 75)))
        prev = cur
    return np.array(out)


def unevenness(m: np.ndarray) -> float:
    """Relative spread of frame-to-frame motion after removing the slow trend: 0 is perfectly even."""
    m = np.maximum(np.asarray(m, float), 1e-6)
    k = min(9, len(m) | 1)
    trend = np.convolve(np.pad(m, k // 2, mode="edge"), np.ones(k) / k, "valid")
    return float(np.std(m / trend))


def positions(m: np.ndarray, n_out: int, step: float, offset: float = 0.0, window: int = 6, equalize: bool = True) -> np.ndarray:
    """Source position (fractional frame index) of every output frame."""
    t = np.minimum((np.arange(n_out) + offset) * step, len(m))
    if not equalize:
        return t
    m = np.maximum(m, 1e-3)
    pad = np.pad(m, (window, window), mode="edge")
    ms = np.convolve(pad, np.ones(window) / window, "same")[window:-window]
    M = np.concatenate([[0], np.cumsum(m)])
    Ms = np.concatenate([[0], np.cumsum(ms)])
    Ms *= M[-1] / Ms[-1]
    j = np.arange(len(M))
    return np.interp(np.interp(t, j, Ms), M, j)


class Rife:
    def __init__(self, threads: int = 4):
        import torch
        from ccvfi import AutoModel, ConfigType

        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if self.device == "cpu":
            torch.set_num_threads(threads)
        self.model = AutoModel.from_pretrained(pretrained_model_name=ConfigType.RIFE_IFNet_v426_heavy, device=self.device, fp16=False)

    def _t(self, f):
        return self.torch.from_numpy(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)).permute(2, 0, 1).float().div(255)

    def between(self, a, b, alpha: float):
        r = self.model.inference(self.torch.stack([self._t(a), self._t(b)]).unsqueeze(0), float(alpha), 1.0)
        return cv2.cvtColor((r[0].clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).round().astype(np.uint8), cv2.COLOR_RGB2BGR)


def main(args):
    pr = Project(args.project)
    rife = None
    for shot in pr.select(args.shot, "smooth"):
        sid, opt = shot["id"], shot["smooth"] if isinstance(shot["smooth"], dict) else {}
        out = pr.frames_dir(sid, "smooth")
        if done(out, args.force):
            continue
        src = [cv2.imread(str(f)) for f in frame_files(pr.latest_frames(sid, before="smooth"))]
        meta = pr.work / "generated" / f"{sid}.json"
        src_fps = float(opt.get("source_fps") or (json.loads(meta.read_text())["fps"] if meta.exists() else pr.fps))
        step = src_fps / pr.fps * float(opt.get("speed", 1.0))  # source frames per output frame
        off = float(opt.get("offset", 0))
        n_out = int(opt.get("frames") or int((len(src) - 1) / step - off) + 1)
        m = motion(src)
        pos = positions(m, n_out, step, off, int(opt.get("window", 6)), bool(opt.get("equalize", True)))
        pos = np.minimum(pos, len(src) - 1.0)
        fresh_dir(out)
        rife = rife or Rife()
        for k, t in enumerate(pos):
            i = int(np.floor(t))
            a = t - i
            if a < 0.03 or i + 1 >= len(src):
                o = src[i]
            elif a > 0.97:
                o = src[i + 1]
            else:
                o = rife.between(src[i], src[i + 1], a)
            cv2.imwrite(str(frame_path(out, k)), o)
        after = unevenness(motion([cv2.imread(str(f)) for f in frame_files(out)]))
        report = {"source_frames": len(src), "frames": n_out, "source_frames_per_frame": round(step, 4),
                  "unevenness_before": round(unevenness(m), 3), "unevenness_after": round(after, 3),
                  "max_shift_vs_uniform": round(float(np.abs(pos - np.minimum((np.arange(n_out) + off) * step, len(src) - 1.0)).max()), 2)}
        (out.parent / "smooth.json").write_text(json.dumps(report, indent=1))
        log(f"{sid}: {report}")
