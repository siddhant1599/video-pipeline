# video-pipeline

A config-driven pipeline for short talking-head videos (ads, explainers, promos). You describe a film in one YAML
file (which footage, which shots, what is said, what appears on screen) and run it stage by stage: cut and clean
footage, generate missing shots, fix stuttering motion, record lines in a reference voice, lip-sync them, upscale to
HD, and cut the film with captions, overlays and an end card in
[HyperFrames](https://github.com/heygen-com/hyperframes).

Everything runs on your own machine except the optional image-to-video generator. No media, model weights or
credentials are part of this repository.

```
 footage, stills ──► ingest ──► clean ──► generate ──► smooth ──┐
                        │                                       ▼
          speech/music  └──► voice ──► mix ──► transcribe ──► lipsync ──► enhance ──► score
                                        │           │                        │
                                        └───────────┴────────► compose ◄─────┘
                                                                  │
                                                               render ──► output/<name>.mp4
```

## What each stage does

| Stage | What it does | Built on | Environment |
|---|---|---|---|
| `ingest` | Cuts shots out of source videos, turns stills into shots, splits a source into speech and music | FFmpeg, Demucs | core |
| `clean` | Removes baked-in text (captions, labels, watermarks you are allowed to remove) from shot frames | OpenCV, LaMa | enhance |
| `generate` | Makes a new shot from a start image and a prompt | Wan 2.2 image-to-video (hosted Space) | core |
| `smooth` | Evens out stuttering motion and retimes a shot to the film's frame rate | optical flow, RIFE 4.26 | enhance |
| `voice` | Records each line in a reference voice, several takes, keeps the one closest to the reference | Chatterbox | voice |
| `mix` | Builds the soundtrack: voice lines, original speech, music bed, effects, ducking | NumPy/SciPy | core |
| `transcribe` | Word timings of the voice track and suggested caption lines | faster-whisper | core |
| `lipsync` | Re-animates the mouth of a shot to the soundtrack | LatentSync | lipsync |
| `enhance` | Upscales every shot to the output size, optional face restoration, writes the shot videos | Real-ESRGAN, GFPGAN | enhance |
| `score` | Measures lip-sync of the finished shots | SyncNet | lipsync |
| `compose` | Writes the HyperFrames project: the cut, captions, overlays, end card | HyperFrames, GSAP | core |
| `render` | Lints, checks, snapshots and renders the film | HyperFrames | core |

## Repository layout

```
video_pipeline/         the tool
  cli.py                command line; starts each stage in the right environment
  config.py             project file, paths, timeline arithmetic
  stages/               one module per stage (the table above)
  synth.py              built-in music bed and sound effects
  vendor/               LatentSync runner and the patches that make it run without a GPU
bin/video-pipeline      launcher (no install needed)
scripts/                setup_*.sh for the environments, models and HyperFrames
requirements/           one requirements file per environment
examples/               project.example.yaml, a starter project file with placeholders
docs/config.md          every key of the project file
tests/                  unit tests for the timing and layout logic
```

Created by the setup scripts and ignored by git: `.venvs/` (Python environments), `models/` (upscaler weights),
`third_party/LatentSync/` (lip-sync code and checkpoints).

A project lives in its own folder, anywhere you like (`projects/` inside the repository is ignored by git):

```
my-video/
  project.yaml          the film
  input/                your footage, images, fonts, voice reference
  work/                 intermediate files (frames, stems, takes, shot videos); safe to delete
  hyperframes/          generated HyperFrames project
  output/               rendered films
```

## Requirements

- Linux or macOS, Python 3.10, FFmpeg 4.4 or newer, Node.js 22 or newer (for HyperFrames).
- About 15 GB of disk for environments and models, 16 GB of RAM.
- A GPU is optional. Everything was built and run on an 8-core CPU; expect roughly 40 s per frame for lip-sync and
  2 to 8 s per frame for upscaling there. The code picks CUDA when PyTorch sees it, but the GPU path has not been run.

## Setup

```bash
git clone <your repository URL> video-pipeline && cd video-pipeline

scripts/setup_core.sh          # CLI, ingest, mix, captions, compose, render
scripts/setup_voice.sh         # Chatterbox
scripts/setup_enhance.sh       # text removal, retiming, upscaling (+ downloads the upscaler weights)
scripts/setup_lipsync.sh       # LatentSync code and checkpoints, patched for CPU
scripts/setup_hyperframes.sh   # checks Node.js/FFmpeg, fetches the headless browser

bin/video-pipeline doctor              # shows what is in place and what is missing
```

`scripts/setup_all.sh` runs all of them. You only need the environments of the stages you use: a film without new
lines needs neither `voice` nor `lipsync`.

There are four environments because the model libraries need different versions of PyTorch and NumPy. The CLI
starts each stage with the right interpreter, so you never activate anything.

| Variable | Purpose |
|---|---|
| `TORCH_INDEX` | PyTorch wheel index used by the setup scripts. Default is the CPU build; set a CUDA index for a GPU |
| `PYTHON` | Interpreter used to create the environments (default `python3`) |
| `VIDEO_PIPELINE_VENVS`, `VIDEO_PIPELINE_MODELS`, `VIDEO_PIPELINE_LATENTSYNC` | Use environments, weights or a LatentSync checkout stored elsewhere |
| `VIDEO_PIPELINE_PY_CORE`, `_VOICE`, `_ENHANCE`, `_LIPSYNC` | Use an existing interpreter for one environment |
| `VIDEO_PIPELINE_HYPERFRAMES` | Command to run HyperFrames (default: `hyperframes` on PATH, else `npx hyperframes@<version>`) |
| `HF_TOKEN` | Hugging Face token for `generate` and the hosted lip-sync backend. Environment only; never put it in a file |

## Quick start

```bash
bin/video-pipeline init projects/my-video           # creates project.yaml from the example
# put your footage, images and fonts in projects/my-video/input, then edit project.yaml

bin/video-pipeline status -p projects/my-video      # the timeline and what exists so far
bin/video-pipeline run    -p projects/my-video      # every stage in order
```

In practice you run stages one at a time and look at the result before the next one:

```bash
P=projects/my-video
bin/video-pipeline ingest     -p $P                 # frames per shot in work/frames/<shot>/raw, stems in work/stems
bin/video-pipeline clean      -p $P                 # work/frames/<shot>/clean
HF_TOKEN=... bin/video-pipeline generate -p $P      # work/generated/<shot>.mp4 and its frames
bin/video-pipeline smooth     -p $P                 # work/frames/<shot>/smooth + smooth.json (stutter before/after)
bin/video-pipeline voice      -p $P                 # work/voice/<line>.wav, all takes in work/voice/takes, rank.json
bin/video-pipeline mix        -p $P                 # work/audio/mix.wav, voice_only.wav, music_only.wav
bin/video-pipeline transcribe -p $P                 # work/audio/words.json, captions.suggested.yaml
bin/video-pipeline lipsync    -p $P                 # work/frames/<shot>/lipsync
bin/video-pipeline enhance    -p $P                 # work/shots/<shot>.mp4 at the output size
bin/video-pipeline score      -p $P                 # work/lipsync/scores.json
bin/video-pipeline compose    -p $P                 # hyperframes/
bin/video-pipeline render     -p $P                 # output/<name>.mp4
```

Useful options: `--shot <id>` and `--line <id>` limit a stage to one shot or line (repeatable), `--force` redoes work
that already exists (stages skip what is done), `video-pipeline run --from mix --to render` runs a range,
`video-pipeline render --no-render` stops after the checks and snapshots.

## The project file

The whole film is in `project.yaml`. A short example:

```yaml
project: {name: my-video, fps: 24, width: 1920, height: 1080}

sources:
  footage: {path: input/footage.mp4, separate: true}

shots:
  - id: talking
    from: {source: footage, start: 5.0, end: 8.75}
    lipsync: {guidance: 2.0}
    enhance: {face: 0.6}

voice:
  reference: {clips: [{source: footage, start: 0.2, end: 4.3}]}
  lines:
    - {id: line1, text: "Here is the line you want her to say.", max_seconds: 3.5}

audio:
  voice: [{line: line1, at: talking+0.1}]
  music: {synth: {bpm: 118}}

timeline: [talking]
tail: 3
captions: {auto: true}
end_card: {brand: "Your brand", headline: "555 010 0199"}
```

Times can be seconds or relative to a shot (`talking+0.1`, `talking.end-1`, `end-3`), so they move with the cut.
[`examples/project.example.yaml`](examples/project.example.yaml) shows every section and
[`docs/config.md`](docs/config.md) explains every key.

## Stage notes

**Shots.** A shot is cut `from` a source, `generate`d, or made from a still `image`. Frames move through
`work/frames/<shot>/raw → clean → smooth → lipsync`; each stage reads the most refined folder that exists, so any
stage can be skipped.

**Generated shots.** `generate` calls a hosted Wan 2.2 image-to-video Space through `gradio_client`. Free quotas are
small and Spaces change; `generate.space` and `generate.api_name` are configurable. A clip from any other generator
works too: add it as a source and cut it with `keep_fps: true`.

**Stutter.** Generated clips often move in uneven steps, which plays as stutter and survives ordinary frame
interpolation. `smooth` measures the motion between frames, places the output frames at even steps of motion, and
synthesises each one at its exact position with RIFE. `smooth.json` reports the unevenness before and after.

**Voice.** Each line is generated several times; takes are ranked by speaker similarity to the reference and the
best one that fits `max_seconds` is kept. Listen to it: similarity does not catch a mispronounced word. Use `say:`
to spell out numbers and names, and `pick: <seed>` to choose another take.

**Lip-sync.** LatentSync runs locally at 25 fps in 16-frame groups. The stage keeps every frame of the shot (frames
are tagged 25 fps and the audio is stretched to match), splits long shots into overlapping segments and cross-fades
the joins. `guidance: 2.0` gave clearly better sync than 1.0 in the film this was built for. The face must be
visible in every frame of the range; limit it with `range`. `backend: hosted` uses a LatentSync Space instead
(needs `HF_TOKEN`, quota-limited, lower quality because the Space re-encodes the video).

**Scores.** `score` reports SyncNet confidence (higher is better; around 7 and up reads as in sync) and the
audio/video offset in frames. Compare versions of the same shot, not different shots. It needs about 2 s of face.

**Upscaling.** `enhance` upscales 4x with Real-ESRGAN and reduces to the output size, then optionally blends GFPGAN
face restoration (`face: 0.6`). Higher face weights look waxy and can change the person's look.

**Soundtrack.** `mix` places lines by time, matches generated lines to a reference passage in tone and loudness,
and ducks the music under speech. The built-in music bed and effects are synthesised by this code, so they carry no
third-party rights; use `music.path` for your own track.

## HyperFrames

`compose` writes a normal HyperFrames project into `<project>/hyperframes/`:

```
index.html                    the cut: one muted <video> per shot, the soundtrack as <audio>
compositions/captions.html    subtitle bar
compositions/overlay-*.html   image panels
compositions/end-card.html    closing card
assets/                       copies of the shot videos, mix, images and fonts
```

`render` then runs the HyperFrames checks in order and stops on lint errors:

```bash
cd projects/my-video/hyperframes
npx hyperframes@0.9.70 lint                 # structure and timing attributes
npx hyperframes@0.9.70 check                # runtime, layout, motion, contrast
npx hyperframes@0.9.70 snapshot --at 1,5,9  # still frames to look at before rendering
npx hyperframes@0.9.70 render --fps 24 -o ../output/my-video.mp4
```

Look at the snapshots before trusting a render; a passing check does not show how a frame looks. `check` warns when
a caption is on screen for less time than it takes to read; captions that follow speech sometimes are.

The generated files follow the HyperFrames rules (timed elements carry `data-start`, `data-duration` and
`class="clip"`, each composition registers one paused GSAP timeline, footage is muted and the sound is one separate
track, nothing depends on the clock or random numbers). You can edit them by hand, but `video-pipeline compose`
overwrites them; for lasting changes edit `video_pipeline/stages/compose.py` or keep your edited copy elsewhere.

## Tests

```bash
.venvs/core/bin/python -m pytest tests     # timing, timeline and layout logic; needs no media or models
```

## Putting this on GitHub

```bash
git init && git add . && git commit -m "video-pipeline"
git remote add origin git@github.com:<you>/<repo>.git
git push -u origin main
```

`.gitignore` keeps media, fonts, model weights, environments, project folders and `.env` files out. Before pushing,
`git status` should list only code and text. Keep `HF_TOKEN` in your shell or a secret manager, never in a file in
the repository.

## Rights and privacy

- You are responsible for the rights to everything you feed in: footage, people's likeness, voices, music, fonts and
  images. Cloning a voice or re-animating a face needs that person's permission. Do not remove watermarks or labels
  from footage you do not have the right to alter.
- The models have their own licences (Wan 2.2, Chatterbox, LatentSync, RIFE, Real-ESRGAN, GFPGAN, LaMa, Demucs,
  Whisper). Check them before commercial use; some weights are non-commercial.
- `generate` and the hosted lip-sync backend upload your image, video and audio to a third-party Space. Everything
  else stays on your machine.
- This repository has no licence file yet. Add one before publishing if others should be able to use it.

## Known limits

- Built from one production and re-run end to end on a small test project after the rewrite (every stage except
  `generate`), on CPU only. `generate` and the hosted lip-sync backend were ported from working scripts but not
  re-run in this form.
- Of the setup scripts, `setup_core.sh` was run from scratch; for the other three environments the requirement
  files were only checked to resolve (`pip install --dry-run`), and the LatentSync download and patch step was run
  without the checkpoints. Expect to adjust a version pin on a different OS or Python.
- SyncNet scoring needs more than 50 frames (2 s) of one face inside a single scene; a shot that crosses a cut or
  is shorter gets no score.
- Give the end card at least 3 s (`tail: 3`), or `hyperframes check` warns that its lines are too short to read.
- Shots are joined with hard cuts; there are no transitions between shots.
- One overlay type (image panel) and one end-card layout. Other graphics mean editing the generated HyperFrames
  project or `compose.py`.
- Lip-sync changes only the mouth region of an existing shot; it cannot fix a hidden or turned-away face.
- Captions are suggested from English word timings by default; set `captions.language` and `captions.whisper_model`
  for other languages, and expect to edit them.
