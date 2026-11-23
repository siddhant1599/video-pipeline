"""Built-in sound: a simple procedural music bed and a few effects.

Meant as a rights-free placeholder so a cut has sound from the first render;
give `audio.music.path` your own licensed track for anything you publish.
Everything is seeded, so the same config always produces the same audio.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt

NOTES = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}


def chord(name: str):
    """'F' or 'Dm' -> ([root, third, fifth, octave] in Hz around octave 3, bass root)."""
    minor = name.endswith("m")
    semis = NOTES[name[:-1] if minor else name]
    root = 130.8128 * 2 ** (semis / 12)
    if semis >= 9:
        root /= 2
    return [root, root * 2 ** ((3 if minor else 4) / 12), root * 2 ** (7 / 12), root * 2], root / 2


class Synth:
    def __init__(self, sr: int, seed: int = 7):
        self.sr, self.rng = sr, np.random.default_rng(seed)

    def tt(self, d):
        return np.arange(int(d * self.sr)) / self.sr

    def filt(self, x, kind, f):
        return sosfilt(butter(2, f, btype=kind, fs=self.sr, output="sos"), x)

    def noise(self, n):
        return self.rng.standard_normal(n)

    def saw(self, f, t, nh=8):
        return sum(np.sin(2 * np.pi * f * k * t) / k for k in range(1, nh + 1) if f * k < 9000)

    def kick(self):
        t = self.tt(0.28)
        ph = 2 * np.pi * np.cumsum(45 + 90 * np.exp(-t / 0.03)) / self.sr
        return np.sin(ph) * np.exp(-t / 0.09) + 0.3 * self.filt(self.noise(len(t)), "high", 2000) * np.exp(-t / 0.004)

    def clap(self):
        t = self.tt(0.22)
        e = np.exp(-t / 0.06) + 0.6 * np.exp(-np.abs(t - 0.012) / 0.004) + 0.6 * np.exp(-np.abs(t - 0.024) / 0.004)
        return self.filt(self.noise(len(t)), "band", [900, 3500]) * e * 0.5

    def hat(self, d=0.03):
        t = self.tt(0.08)
        return self.filt(self.noise(len(t)), "high", 7000) * np.exp(-t / d) * 0.25

    def pluck(self, f, d=0.32, dec=0.11):
        t = self.tt(d)
        return (self.saw(f, t, 7) + self.saw(f * 1.004, t, 7)) * np.exp(-t / dec) * 0.18

    def bass(self, f, d=0.23):
        t = self.tt(d)
        return self.filt(self.saw(f, t, 5), "low", 420) * np.minimum(1, t / 0.005) * np.exp(-t / 0.16) * 0.5

    # ---- effects -----------------------------------------------------------
    def effect(self, name: str, seconds: float | None = None):
        if name == "riser":
            t = self.tt(seconds or 2.0)
            return self.filt(self.noise(len(t)), "high", 1500) * (t / t[-1]) ** 2.5 * 0.35
        if name == "whoosh":
            d = seconds or 1.7
            t = self.tt(d)
            w = self.noise(len(t))
            e = np.sin(np.pi * np.minimum(1, t / d)) ** 1.5
            return (self.filt(w, "band", [300, 1400]) * 0.9 + self.filt(w, "band", [1400, 4000]) * 0.5 * (t / d)) * e * 0.55
        if name == "impact":
            t = self.tt(seconds or 0.9)
            boom = np.sin(2 * np.pi * (38 + 30 * np.exp(-t / 0.05)) * t) * np.exp(-t / 0.25)
            return boom * 0.45 + self.filt(self.noise(len(t)), "high", 4000) * np.exp(-t / 0.3) * 0.15
        if name == "pop":
            t = self.tt(seconds or 0.12)
            f = 520 + 360 * np.minimum(1, t / 0.05)
            return np.sin(2 * np.pi * np.cumsum(f) / self.sr) * np.exp(-t / 0.035) * 0.5
        if name == "ding":
            t = self.tt(seconds or 0.6)
            return (np.sin(2 * np.pi * 1318.5 * t) + 0.6 * np.sin(2 * np.pi * 1975.5 * t)) * np.exp(-t / 0.18) * 0.25
        raise ValueError(f"unknown built-in effect '{name}' (riser, whoosh, impact, pop, ding)")

    # ---- music bed ---------------------------------------------------------
    def bed(self, n: int, bpm: float = 120, chords=("F", "C", "Dm", "Bb"), drums_from: float = 0.0, end: float | None = None):
        """Plucked arpeggio + bass over a four-chord loop; drums join at `drums_from`; a last chord rings out at `end`."""
        buf = np.zeros(n)
        prog = [chord(c) for c in chords]
        beat = 60.0 / bpm
        end = n / self.sr if end is None else end

        def place(sig, at, gain=1.0):
            i = int(round(at * self.sr))
            m = min(len(sig), n - i)
            if m > 0 and i >= 0:
                buf[i:i + m] += sig[:m] * gain

        b = 0
        while b * beat < end - 0.01:
            at = b * beat
            notes, root = prog[(b // 4) % len(prog)]
            drums = at >= drums_from
            level = 1.0 if drums else 0.7
            if drums:
                place(self.kick(), at, 0.9)
                if b % 2 == 1:
                    place(self.clap(), at, 0.8)
                place(self.hat(), at + beat / 2, 0.8)
                place(self.hat(0.015), at + beat / 4, 0.35)
                place(self.hat(0.015), at + 3 * beat / 4, 0.35)
            place(self.bass(root), at, 0.9 * level)
            place(self.bass(root * 2 if b % 2 else root), at + beat / 2, 0.7 * level)
            pat = [0, 2, 1, 3] if (b % 4) < 2 else [3, 1, 2, 0]
            place(self.pluck(notes[pat[b % 4]] * 2), at, 0.9 * level)
            place(self.pluck(notes[pat[(b + 1) % 4]] * 2), at + beat / 2, 0.7 * level)
            if b % 4 == 0:
                for f in notes:
                    place(self.pluck(f * 2, 0.5, 0.2), at, 0.45 * level)
            b += 1
        t = self.tt(3.0)
        notes, root = prog[0]
        for f in notes + [root]:
            place((self.saw(f * 2, t, 6) * 0.5 + np.sin(2 * np.pi * f * t)) * np.exp(-t / 1.1) * 0.12, end)
        place(self.kick(), end, 0.9)
        return buf
