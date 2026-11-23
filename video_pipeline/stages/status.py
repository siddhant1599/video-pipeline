"""status: the timeline and what each stage has produced so far."""
from __future__ import annotations

from ..config import FRAME_STAGES, Project


def main(args):
    pr = Project(args.project)
    print(f"{pr.name}: {pr.width}x{pr.height} at {pr.fps:g} fps, {pr.duration():.2f} s")
    print(f"project file: {pr.file}\n")
    on_tl = {i["shot"]: i for i in pr.timeline()}
    print(f"{'shot':<16}{'kind':<10}{'start':>8}{'frames':>8}  frames on disk" + " " * 22 + "video")
    for sid, s in pr.shots.items():
        kind = next(k for k in ("from", "generate", "image") if k in s)
        have = []
        for st in FRAME_STAGES:
            d = pr.frames_dir(sid, st)
            n = len(list(d.glob("*.png"))) if d.is_dir() else 0
            have.append(f"{st}:{n}" if n else f"{st}:-")
        i = on_tl.get(sid)
        start = f"{i['start']:.2f}" if i else "(off)"
        print(f"{sid:<16}{kind:<10}{start:>8}{pr.shot_frames(sid):>8}  {' '.join(have):<36}{'yes' if pr.shot_video(sid).exists() else '-'}")
    print()
    for sid, s in pr.sources.items():
        sep = isinstance(s, dict) and s.get("separate")
        print(f"source {sid}: {'found' if pr.source_path(sid).exists() else 'MISSING'}"
              + (f", speech/music split: {'yes' if pr.stem(sid).exists() else '-'}" if sep else ""))
    for lid in pr.lines:
        print(f"voice line {lid}: {'recorded' if pr.line_wav(lid).exists() else '-'}")
    for name, p in (("soundtrack", pr.audio_dir / "mix.wav"), ("word timings", pr.audio_dir / "words.json"),
                    ("HyperFrames project", pr.hf / "index.html"), ("film", pr.out / f"{pr.name}.mp4")):
        print(f"{name}: {p if p.exists() else '-'}")
