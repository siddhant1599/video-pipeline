"""mix: build the soundtrack on the film's timeline.

- voice: generated lines and passages of original speech, placed at their times;
  generated lines can be matched in tone (gentle long-term EQ) and loudness to a
  reference passage so all lines sound like one recording.
- music: your own track, or the built-in procedural bed; it ducks under speech.
- effects: your own files or the built-in ones.

Writes `mix.wav` (stereo), `voice_only.wav` (what lip-sync and captions use) and
`music_only.wav` into `work/audio/`.
"""
from __future__ import annotations

from math import gcd

import numpy as np
import soundfile as sf
from scipy.signal import butter, resample_poly, sosfilt, welch

from ..config import Project
from ..synth import Synth
from ..util import log


def load(path, sr):
    x, s = sf.read(str(path))
    x = x.mean(1) if x.ndim > 1 else x
    if s != sr:
        g = gcd(int(sr), int(s))
        x = resample_poly(x, int(sr) // g, int(s) // g)
    return x


def rms_active(x):
    a = np.abs(x) > 0.05 * np.abs(x).max()
    return float(np.sqrt((x[a] ** 2).mean())) if a.any() else 0.0


def eq_match(x, target, sr, max_db=6.0):
    """Gentle long-term spectrum match of `x` to `target` (1/3-octave smoothed, limited to +-max_db)."""
    def ltas(y):
        return welch(y[np.abs(y) > 0.03 * np.abs(y).max()], sr, nperseg=4096)

    f, pt = ltas(target)
    _, px = ltas(x)
    g = 10 * np.log10((pt + 1e-12) / (px + 1e-12))
    lf = np.log2(np.maximum(f, 20))
    gs = np.array([g[np.abs(lf - l) < 1 / 3].mean() for l in lf])
    gs -= gs[(f > 300) & (f < 3000)].mean()
    gs = np.clip(gs, -max_db, max_db)
    gs[(f < 80) | (f > 9000)] = 0
    X = np.fft.rfft(x)
    return np.fft.irfft(X * 10 ** (np.interp(np.fft.rfftfreq(len(x), 1 / sr), f, gs) / 20), len(x))


def faded(x, sr, seconds=0.04):
    k = min(int(seconds * sr), len(x) // 2)
    x = x.copy()
    if k:
        x[:k] *= np.linspace(0, 1, k)
        x[-k:] *= np.linspace(1, 0, k)
    return x


def main(args):
    pr = Project(args.project)
    au = pr.audio
    sr = int(au.get("sample_rate", 44100))
    total = pr.duration()
    n = int(round(total * sr))
    voice, music, sfx = np.zeros(n), np.zeros(n), np.zeros(n)

    def place(buf, sig, at, gain=1.0):
        i = int(round(at * sr))
        if i < 0:
            sig, i = sig[-i:], 0
        m = min(len(sig), n - i)
        if m > 0:
            buf[i:i + m] += sig[:m] * gain

    def passage(spec):
        """A stretch of a source's separated stem, or of any audio file."""
        src = pr.path(spec["path"]) if "path" in spec else pr.stem(spec["source"], spec.get("stem", "vocals"))
        if not src.exists():
            raise SystemExit(f"[video-pipeline] error: {src} is missing (for a source, set `separate: true` and run `video-pipeline ingest`)")
        x = load(src, sr)
        return x[int(float(spec.get("start", 0)) * sr): int(float(spec["end"]) * sr) if "end" in spec else len(x)]

    # ---- voice -------------------------------------------------------------
    match = au.get("voice_match") or {}
    ref = passage(match["reference"]) if match.get("reference") else None
    target = rms_active(ref) if ref is not None else None
    pieces = []
    for v in au.get("voice") or []:
        at = pr.time(v.get("at", 0))
        if "line" in v:
            wav = pr.line_wav(v["line"])
            if not wav.exists():
                raise SystemExit(f"[video-pipeline] error: {wav} is missing; run `video-pipeline voice`")
            x = load(wav, sr)
            if "max_seconds" in v:
                x = x[: int(float(v["max_seconds"]) * sr)]
            x = sosfilt(butter(2, 70, btype="high", fs=sr, output="sos"), x)
            if ref is not None and match.get("eq", True):
                x = eq_match(x, ref, sr, float(match.get("max_db", 6.0)))
            x = faded(x, sr, 0.02)
            pieces.append((x, at, float(v.get("gain", 1.0)), True))
        else:
            pieces.append((faded(passage(v), sr), at, float(v.get("gain", 1.0)), False))
    if target is None and pieces:
        target = float(np.median([rms_active(x) for x, *_ in pieces]))
    for x, at, gain, generated in pieces:
        if generated and match.get("loudness", True) and rms_active(x) > 0:
            x = x * target / rms_active(x)
        place(voice, x, at, gain)

    # ---- music and effects -------------------------------------------------
    mu = au.get("music") or {}
    synth = Synth(sr, int((mu.get("synth") or {}).get("seed", 7)))
    if mu.get("path"):
        x = load(pr.path(mu["path"]), sr)
        if mu.get("loop") and len(x) < n:
            x = np.tile(x, int(np.ceil(n / len(x))))
        place(music, x, pr.time(mu.get("at", 0)))
    elif "synth" in mu:
        s = mu["synth"] or {}
        music = synth.bed(n, float(s.get("bpm", 120)), s.get("chords", ["F", "C", "Dm", "Bb"]),
                          pr.time(s.get("drums_from", 0)), pr.time(s["end"]) if "end" in s else None)
    for e in au.get("sfx") or []:
        x = load(pr.path(e["path"]), sr) if "path" in e else synth.effect(e["builtin"], e.get("seconds"))
        place(sfx, x, pr.time(e.get("at", 0)), float(e.get("gain", 1.0)))

    # ---- duck music under speech, master -----------------------------------
    k = int(0.25 * sr)
    env = np.convolve(np.abs(voice), np.ones(k) / k, "same")
    presence = np.clip(env / (0.25 * target), 0, 1) if target else np.zeros(n)
    if np.abs(music).max() > 0:
        music = music / np.abs(music).max()
    bed = music * (float(mu.get("gain", 0.34)) - float(mu.get("duck", 0.17)) * presence) + sfx * float(au.get("sfx_gain", 0.55))
    ma = au.get("master") or {}
    fade = np.ones(n)
    fo = int(float(ma.get("fade_out", 0.6)) * sr)
    if fo:
        fade[-fo:] = np.linspace(1, 0, fo)
    mix = np.tanh((voice + bed) * fade * float(ma.get("drive", 1.1)))
    mix = mix / max(np.abs(mix).max(), 1e-9) * float(ma.get("peak", 0.89))
    pr.audio_dir.mkdir(parents=True, exist_ok=True)
    sf.write(pr.audio_dir / "mix.wav", np.stack([mix, mix], 1), sr)
    sf.write(pr.audio_dir / "voice_only.wav", voice, sr)
    sf.write(pr.audio_dir / "music_only.wav", bed * fade, sr)
    log(f"soundtrack {total:.2f} s, {len(pieces)} voice piece(s) -> {pr.audio_dir / 'mix.wav'}")
