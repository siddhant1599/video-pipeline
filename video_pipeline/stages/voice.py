"""voice: record the spoken lines in a reference voice with Chatterbox.

For every line several takes are generated (different seeds). Each take is
scored by speaker similarity to the reference (Chatterbox's own voice encoder,
cosine similarity), and the best take that fits the line's `max_seconds` is
copied to `work/voice/<line>.wav`. Set `pick: <seed>` on a line to choose a
take by ear instead; `work/voice/rank.json` lists every take.

Only use a voice you have the right to use.
"""
from __future__ import annotations

import json
import shutil

import numpy as np

from ..config import Project
from ..util import done, ffmpeg, log


def build_reference(pr: Project, force: bool):
    ref = pr.voice.get("reference") or {}
    if isinstance(ref, str):
        ref = {"path": ref}
    if "path" in ref:
        return pr.path(ref["path"])
    out = pr.work / "voice" / "ref.wav"
    if out.exists() and not force:
        return out
    import soundfile as sf

    out.parent.mkdir(parents=True, exist_ok=True)
    parts, sr = [], None
    for c in ref.get("clips") or []:
        src = pr.stem(c["source"], c.get("stem", "vocals"))
        if not src.exists():
            raise SystemExit(f"[video-pipeline] error: {src} is missing; set `separate: true` on source '{c['source']}' and run `video-pipeline ingest`")
        x, sr = sf.read(src)
        x = x.mean(1) if x.ndim > 1 else x
        parts += [x[int(float(c["start"]) * sr): int(float(c["end"]) * sr)], np.zeros(int(0.12 * sr))]
    if not parts:
        raise SystemExit("[video-pipeline] error: voice.reference needs `path` or `clips`")
    sf.write(out, np.concatenate(parts[:-1]), sr)
    log(f"voice reference built from {len(parts) // 2} clip(s): {out}")
    return out


def main(args):
    pr = Project(args.project)
    lines = [l for l in pr.lines.values() if not args.line or l["id"] in args.line]
    if not lines:
        return
    import librosa
    import soundfile as sf
    import torch
    from chatterbox.tts import ChatterboxTTS

    ref = build_reference(pr, args.force)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = ChatterboxTTS.from_pretrained(device=device)

    def embed(wav_path):
        w, _ = librosa.load(str(wav_path), sr=16000)
        e = np.asarray(model.ve.embeds_from_wavs([w], sample_rate=16000)).reshape(-1)
        return w, e / np.linalg.norm(e)

    _, ref_emb = embed(ref)
    defaults = {"takes": 4, "seed": 11, "exaggeration": 0.6, "cfg_weight": 0.5, "temperature": 0.8, **(pr.voice.get("defaults") or {})}
    rank_file = pr.work / "voice" / "rank.json"
    rank = json.loads(rank_file.read_text()) if rank_file.exists() else {}
    for line in lines:
        o = {**defaults, **line}
        takes_dir = pr.work / "voice" / "takes" / line["id"]
        takes_dir.mkdir(parents=True, exist_ok=True)
        final = pr.line_wav(line["id"])
        if done(final, args.force):
            continue
        scored = {}
        for seed in range(int(o["seed"]), int(o["seed"]) + int(o["takes"])):
            take = takes_dir / f"seed{seed}.wav"
            if not take.exists() or args.force:
                torch.manual_seed(seed)
                wav = model.generate(o.get("say", o["text"]), audio_prompt_path=str(ref), exaggeration=float(o["exaggeration"]),
                                     cfg_weight=float(o["cfg_weight"]), temperature=float(o["temperature"]))
                sf.write(take, wav.squeeze(0).cpu().numpy(), model.sr)
            w, e = embed(take)
            iv = librosa.effects.split(w, top_db=35)
            scored[str(seed)] = {"similarity": round(float(e @ ref_emb), 3), "seconds": round(len(w) / 16000, 2),
                                 "speech_seconds": round(float((iv[-1][1] - iv[0][0]) / 16000), 2)}
            log(f"{line['id']} seed {seed}: {scored[str(seed)]}")
        fits = {s: v for s, v in scored.items() if "max_seconds" not in o or v["speech_seconds"] <= float(o["max_seconds"])} or scored
        pick = str(o["pick"]) if str(o.get("pick", "best")) != "best" else max(fits, key=lambda s: fits[s]["similarity"])
        if pick not in scored:
            raise SystemExit(f"[video-pipeline] error: line '{line['id']}': pick {pick} is not one of the takes {sorted(scored)}")
        shutil.copy(takes_dir / f"seed{pick}.wav", final)
        rank[line["id"]] = {"picked": pick, "takes": scored}
        rank_file.write_text(json.dumps(rank, indent=1))
        log(f"{line['id']}: picked seed {pick} -> {final}")
