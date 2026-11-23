"""transcribe: word timings of the voice track (faster-whisper), for captions.

Writes `work/audio/words.json` and `work/audio/captions.suggested.yaml`, a ready
`captions.items` block you can paste into the project file and edit. With
`captions: {auto: true}` the compose stage uses the suggestion directly.
"""
from __future__ import annotations

import json

import yaml

from ..config import Project
from ..util import log


def group(words: list[dict], max_chars: int = 34, max_gap: float = 0.45, min_hold: float = 0.9) -> list[dict]:
    """Split words into caption lines: phrases end at pauses and sentence ends, long phrases are split into even lines."""
    phrases, cur = [], []
    for w in words:
        if cur and (w["start"] - cur[-1]["end"] > max_gap or cur[-1]["word"][-1:] in ".?!"):
            phrases.append(cur)
            cur = []
        cur.append(w)
    if cur:
        phrases.append(cur)
    lines = []
    for ph in phrases:
        total = len(" ".join(x["word"] for x in ph))
        target = total / max(1, -(-total // max_chars))  # even line length, so no one-word leftovers
        cur = []
        for w in ph:
            text = " ".join(x["word"] for x in cur + [w])
            before = len(" ".join(x["word"] for x in cur))
            if cur and (len(text) > max_chars or (before >= target * 0.8 and abs(before - target) <= abs(len(text) - target))):
                lines.append(cur)
                cur = []
            cur.append(w)
        if cur:
            lines.append(cur)
    out = []
    for i, l in enumerate(lines):
        end = l[-1]["end"]
        nxt = lines[i + 1][0]["start"] if i + 1 < len(lines) else None
        end = max(end, l[0]["start"] + min_hold)  # hold short lines long enough to read
        if nxt is not None:
            end = min(end, nxt - 0.02) if end > nxt - 0.02 else max(end, min(nxt - 0.02, end + 0.25))
        out.append({"text": " ".join(x["word"] for x in l), "start": round(float(l[0]["start"]), 2), "end": round(float(end), 2)})
    return out


def main(args):
    pr = Project(args.project)
    wav = pr.audio_dir / "voice_only.wav"
    if not wav.exists():
        raise SystemExit(f"[video-pipeline] error: {wav} is missing; run `video-pipeline mix`")
    from faster_whisper import WhisperModel

    opt = pr.cfg.get("captions") or {}
    model = WhisperModel(opt.get("whisper_model", "small.en"), device="cpu", compute_type="int8")
    segs, _ = model.transcribe(str(wav), word_timestamps=True, language=opt.get("language", "en"))
    words = [{"word": w.word.strip(), "start": round(float(w.start), 3), "end": round(float(w.end), 3)} for s in segs for w in s.words]
    (pr.audio_dir / "words.json").write_text(json.dumps(words, indent=1))
    items = group(words, int(opt.get("max_chars", 34)))
    (pr.audio_dir / "captions.suggested.yaml").write_text(yaml.safe_dump({"captions": {"items": items}}, sort_keys=False, allow_unicode=True))
    log(f"{len(words)} words, {len(items)} suggested caption lines -> {pr.audio_dir / 'captions.suggested.yaml'}")
