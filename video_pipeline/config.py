"""Project config: loading, defaults, paths and timeline arithmetic.

Everything a stage needs to know about a project comes from here, so no stage
contains a file name, frame number or timing of its own.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

FRAME_STAGES = ["raw", "clean", "smooth", "lipsync"]  # order in which a shot's frames are refined
FRAME_PATTERN = "%05d.png"


class ConfigError(Exception):
    pass


class Project:
    def __init__(self, path: str | os.PathLike):
        self.file = Path(path).resolve()
        if self.file.is_dir():
            self.file = self.file / "project.yaml"
        if not self.file.exists():
            raise ConfigError(f"project file not found: {self.file}")
        self.root = self.file.parent
        self.cfg = yaml.safe_load(self.file.read_text()) or {}
        p = self.cfg.get("project") or {}
        self.name = p.get("name", self.root.name)
        self.fps = float(p.get("fps", 24))
        self.width = int(p.get("width", 1920))
        self.height = int(p.get("height", 1080))
        paths = self.cfg.get("paths") or {}
        self.work = self.path(paths.get("work", "work"))
        self.out = self.path(paths.get("output", "output"))
        self.hf = self.path(paths.get("hyperframes", "hyperframes"))
        self.shots = {s["id"]: s for s in self.cfg.get("shots") or []}
        self.sources = self.cfg.get("sources") or {}
        self.voice = self.cfg.get("voice") or {}
        self.lines = {l["id"]: l for l in self.voice.get("lines") or []}
        self.audio = self.cfg.get("audio") or {}
        self.validate()

    # ---- paths -------------------------------------------------------------
    def path(self, p) -> Path:
        """Resolve a path from the config relative to the project file."""
        p = Path(os.path.expanduser(str(p)))
        return p if p.is_absolute() else self.root / p

    def source_path(self, sid: str) -> Path:
        if sid not in self.sources:
            raise ConfigError(f"unknown source '{sid}' (sources: {', '.join(self.sources) or 'none'})")
        s = self.sources[sid]
        return self.path(s["path"] if isinstance(s, dict) else s)

    def frames_dir(self, shot: str, stage: str) -> Path:
        return self.work / "frames" / shot / stage

    def latest_frames(self, shot: str, before: str | None = None) -> Path:
        """Most refined frame folder of a shot, optionally only stages before `before`."""
        stages = FRAME_STAGES if before is None else FRAME_STAGES[: FRAME_STAGES.index(before)]
        for st in reversed(stages):
            d = self.frames_dir(shot, st)
            if d.is_dir() and any(d.glob("*.png")):
                return d
        raise ConfigError(f"shot '{shot}' has no frames yet (run `video-pipeline ingest`, or `video-pipeline generate` for generated shots)")

    def shot_video(self, shot: str) -> Path:
        return self.work / "shots" / f"{shot}.mp4"

    def stem(self, source: str, stem: str = "vocals") -> Path:
        return self.work / "stems" / source / f"{stem}.wav"

    def line_wav(self, line: str) -> Path:
        return self.work / "voice" / f"{line}.wav"

    @property
    def audio_dir(self) -> Path:
        return self.work / "audio"

    # ---- shots and timeline -----------------------------------------------
    def shot_frames(self, shot: str) -> int:
        """Length of a shot in frames: a declared retime target, else what is on disk, else what the config implies."""
        smooth = self.shots[shot].get("smooth")
        if isinstance(smooth, dict) and "frames" in smooth:
            return int(smooth["frames"])
        # a shot that will be retimed has its final length only once `smooth` has run
        stages = FRAME_STAGES[FRAME_STAGES.index("smooth"):] if smooth else FRAME_STAGES
        for st in reversed(stages):
            d = self.frames_dir(shot, st)
            if d.is_dir():
                n = len(list(d.glob("*.png")))
                if n:
                    return n
        return self.declared_frames(shot)

    def declared_frames(self, shot: str) -> int:
        """Length the config implies, before anything is on disk."""
        s = self.shots[shot]
        smooth = s.get("smooth") if isinstance(s.get("smooth"), dict) else {}
        if "frames" in smooth:
            return int(smooth["frames"])
        speed = float(smooth.get("speed", 1.0))
        if "from" in s:
            f = s["from"]
            if f.get("keep_fps"):
                if "end" not in f:
                    raise ConfigError(f"shot '{shot}': with `keep_fps` give `start`/`end` in seconds, or set `smooth.frames`")
                return int(round((float(f["end"]) - float(f.get("start", 0))) * self.fps / speed))
            a, b = self.frame_range(f)
            return int(round((b - a) / speed))
        if "generate" in s:
            return int(round(float(s["generate"].get("seconds", 5)) * self.fps / speed))
        if "frames" in s:
            return int(s["frames"])
        return int(round(float(s.get("seconds", 3)) * self.fps))

    def frame_range(self, spec: dict) -> tuple[int, int]:
        """`start`/`end` in seconds or `start_frame`/`end_frame`, as project-fps frame numbers."""
        if "start_frame" in spec or "end_frame" in spec:
            return int(spec.get("start_frame", 0)), int(spec["end_frame"])
        return int(round(float(spec.get("start", 0)) * self.fps)), int(round(float(spec["end"]) * self.fps))

    def timeline(self) -> list[dict]:
        """Shots in film order with `start`, `duration` and `frames` filled in."""
        out, t = [], 0.0
        for item in self.cfg.get("timeline") or []:
            item = {"shot": item} if isinstance(item, str) else dict(item)
            sid = item["shot"]
            if sid not in self.shots:
                raise ConfigError(f"timeline uses unknown shot '{sid}'")
            n = self.shot_frames(sid)
            if "at" in item:
                t = float(item["at"])
            item.update(start=round(t, 4), frames=n, duration=round(n / self.fps, 4))
            out.append(item)
            t += n / self.fps
        return out

    def duration(self) -> float:
        tl = self.timeline()
        end = max((i["start"] + i["duration"] for i in tl), default=0.0)
        return round(end + float(self.cfg.get("tail", 0)), 4)

    def shot_start(self, shot: str) -> float:
        for i in self.timeline():
            if i["shot"] == shot:
                return i["start"]
        raise ConfigError(f"shot '{shot}' is not on the timeline")

    _REST = re.compile(r"^(\.end)?\s*(?:([+-])\s*(\d+(?:\.\d+)?))?$")

    def time(self, expr) -> float:
        """A time on the film: seconds, or 'shot', 'shot+1.5', 'shot.end-0.5', 'start', 'end-3'."""
        if isinstance(expr, (int, float)):
            return float(expr)
        text = str(expr).strip()
        try:
            return float(text)
        except ValueError:
            pass
        tl = {i["shot"]: i for i in self.timeline()}
        for name in sorted([*tl, "start", "end"], key=len, reverse=True):  # longest name first: ids may contain '-'
            if not text.startswith(name):
                continue
            m = self._REST.match(text[len(name):].strip())
            if not m:
                continue
            at_end, sign, off = m.groups()
            off = float(off or 0) * (-1 if sign == "-" else 1)
            if name in tl:
                return round(tl[name]["start"] + (tl[name]["duration"] if at_end else 0) + off, 4)
            if at_end:
                continue
            return round((self.duration() if name == "end" else 0.0) + off, 4)
        raise ConfigError(f"cannot read time '{expr}' (use seconds, 'shot+1.5', 'shot.end-0.5', 'start+1' or 'end-3')")

    # ---- checks ------------------------------------------------------------
    def validate(self):
        seen = set()
        for s in self.cfg.get("shots") or []:
            if "id" not in s:
                raise ConfigError("every shot needs an `id`")
            if not re.fullmatch(r"[A-Za-z_][\w-]*", s["id"]) or s["id"] in ("start", "end"):
                raise ConfigError(f"shot id '{s['id']}' must be a simple name (letters, digits, - and _) other than start/end")
            if s["id"] in seen:
                raise ConfigError(f"duplicate shot id '{s['id']}'")
            seen.add(s["id"])
            kinds = [k for k in ("from", "generate", "image") if k in s]
            if len(kinds) != 1:
                raise ConfigError(f"shot '{s['id']}' needs exactly one of `from`, `generate`, `image`")
            if "from" in s and s["from"].get("source") not in self.sources:
                raise ConfigError(f"shot '{s['id']}' uses unknown source '{s['from'].get('source')}'")
            if "from" in s and s["from"].get("keep_fps") and not s.get("smooth"):
                raise ConfigError(f"shot '{s['id']}': `keep_fps` keeps the source's own frames, so the shot needs a `smooth:` block to bring it to the project frame rate")
        for v in self.audio.get("voice") or []:
            if "line" in v and v["line"] not in self.lines:
                raise ConfigError(f"audio.voice uses unknown line '{v['line']}'")
        for item in self.cfg.get("timeline") or []:
            sid = item if isinstance(item, str) else item.get("shot")
            if sid not in self.shots:
                raise ConfigError(f"timeline uses unknown shot '{sid}'")

    def select(self, only: list[str] | None, key: str | None = None) -> list[dict]:
        """Shots to work on: those named with --shot, else all (that have `key` set)."""
        shots = list(self.shots.values())
        if only:
            missing = [s for s in only if s not in self.shots]
            if missing:
                raise ConfigError(f"unknown shot(s): {', '.join(missing)}")
            shots = [self.shots[s] for s in only]
        return [s for s in shots if key is None or s.get(key)]
