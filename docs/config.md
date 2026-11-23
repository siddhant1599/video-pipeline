# The project file

One YAML file describes a film. Paths are relative to the file. A starter copy is in
[`examples/project.example.yaml`](../examples/project.example.yaml); `video-pipeline init <dir>` puts it in a new folder.

## Times

Anywhere a time on the film is expected you can write seconds (`12.5`) or an expression:

| Expression | Meaning |
|---|---|
| `talking` | the start of shot `talking` on the timeline |
| `talking+0.2` | 0.2 s after it starts |
| `talking.end-1` | 1 s before it ends |
| `start+1`, `end-3` | from the start / end of the film |

Times given this way move with the shots, so re-cutting a shot does not mean re-timing everything after it.

## `project`

| Key | Default | Meaning |
|---|---|---|
| `name` | folder name | Name of the film and of the rendered file |
| `fps` | 24 | Frame rate of the film |
| `width`, `height` | 1920, 1080 | Output size. Shots are centre-cropped to this aspect ratio |
| `hyperframes_version` | 0.9.70 | HyperFrames release used through `npx` |

## `paths`

`work` (default `work`), `output` (`output`), `hyperframes` (`hyperframes`): where intermediate files, renders and
the generated HyperFrames project go.

## `sources`

```yaml
sources:
  footage: {path: input/footage.mp4, separate: true}
```

`separate: true` splits the source into speech (`vocals`) and everything else (`no_vocals`) with Demucs. It is needed
when you reuse the source's speech in the soundtrack or use it as the voice reference.

## `shots`

Every shot has an `id` and exactly one of `from`, `generate`, `image`.

| Key | Meaning |
|---|---|
| `from: {source, start, end}` | Cut from a source, in seconds (or `start_frame` / `end_frame`, counted at the project frame rate). `crop: [x, y, w, h]` crops in source pixels |
| `from: {..., keep_fps: true}` | Keep the clip's own frames instead of converting to the project frame rate. Use it for a clip made by a video generator; the shot then needs `smooth:` |
| `generate: {image, prompt, seconds, seed}` | New shot from a start image. `image` is a path or `{shot: id, frame: n}` (a frame of another shot; negative counts from the end). `end_image` is optional. Any key of the top-level `generate:` block can be overridden here |
| `image: {path, zoom: [from, to], center: [x, y]}` + `seconds` or `frames` | A still, with an optional slow push-in toward `center` (fractions of the frame) |
| `clean: [{boxes, frames, mode}]` | Remove baked-in text. `boxes` are `[x0, y0, x1, y1]` in source pixels, `frames: [first, last)` limits the rule, `mode: text` (default) removes only bright text pixels inside the boxes, `mode: box` the whole box. Tuning: `threshold`, `min_value`, `grow`, `kernel` |
| `smooth: {speed, frames, equalize, window, offset, source_fps}` | Even out stutter and retime. `speed` below 1 slows the shot down, `frames` fixes the output length, `equalize: false` only retimes |
| `lipsync: {guidance, steps, seed, range, max_frames, backend}` | Re-animate the mouth to the soundtrack. `range: [first, last)` limits it to frames where the face is visible. `guidance` 2.0 follows the audio closely, 1.0 changes the face less. `backend: hosted` uses a Space instead of the local model |
| `enhance: {face, upscale, crop}` | `face: 0.6` blends GFPGAN face restoration in at that weight (0 = off). `upscale: false` only resizes |

## `generate` (top level, optional)

Defaults for all generated shots: `space`, `api_name`, `steps`, `guidance_scale`, `guidance_scale_2`, `seed`,
`seconds`. The defaults point at a public Wan 2.2 image-to-video Space; hosted Spaces come and go, so change `space`
and `api_name` when it does.

## `voice`

| Key | Meaning |
|---|---|
| `reference.path` | A recording of the voice to speak in |
| `reference.clips: [{source, start, end}]` | Or passages of a separated source, joined into the reference. 10 to 20 s of clean speech works well |
| `defaults` | `takes` (4), `seed` (11), `exaggeration` (0.6), `cfg_weight` (0.5), `temperature` (0.8) |
| `lines: [{id, text, say, max_seconds, pick}]` | `say` is what is actually spoken when it differs from the caption text (numbers, names spelled the way they sound). `max_seconds` rejects takes that are too long. `pick: <seed>` chooses a take by ear instead of by score. Any default can be set per line |

## `audio`

| Key | Meaning |
|---|---|
| `sample_rate` | 44100 |
| `voice: [{line, at}]` | Place a generated line on the film |
| `voice: [{source, start, end, at}]` | Place a passage of a source's separated speech (`stem: no_vocals` for the rest), or `path:` for any audio file |
| `voice_match.reference` | A passage (same form as above) that generated lines are matched to in tone and loudness. `eq: false` / `loudness: false` turn either off, `max_db` (6) limits the tone correction |
| `music.path` | Your own music (`loop: true` repeats it) |
| `music.synth` | Or the built-in procedural bed: `bpm`, `chords`, `drums_from`, `end`, `seed` |
| `music.gain`, `music.duck` | Music level (0.34) and how much it drops under speech (0.17) |
| `sfx: [{builtin \| path, at, gain}]` | Built-in effects: `whoosh`, `riser`, `impact`, `pop`, `ding` |
| `master` | `fade_out` (0.6 s), `peak` (0.89), `drive` (1.1) |

## `timeline` and `tail`

`timeline` lists shot ids in film order. Shots follow each other without gaps; `{shot: id, at: 12.0}` places one at an
absolute time instead. `tail` adds seconds after the last shot, for the end card.

## `captions`

`auto: true` uses the lines suggested by `video-pipeline transcribe`. `items: [{text, start, end}]` sets them by hand;
`*word*` highlights a word in the accent colour. Style: `size` (62), `bottom` (84), `weight` (700), `bar` (CSS
colour of the bar), `max_chars` (34, for the suggestion), `whisper_model` (`small.en`), `language` (`en`).
Sizes are in pixels for a 1080-line frame and scale with the output size. Captions shown while a panel is open are
centred in the part of the frame the panel leaves free.

## `overlays`

One kind, an image panel that slides in from a side:

| Key | Meaning |
|---|---|
| `id` | Name of the generated composition (`compositions/overlay-<id>.html`) |
| `side`, `size` | `left`, `right`, `top` or `bottom`, and its width (or height) |
| `start`, `end` | When it slides in and when it starts to slide away |
| `push_shot`, `push` | Slide that shot's footage aside by `push` pixels (default: half the panel) so the subject stays in view |
| `images: [{path, alt, in, out, width}]` | Images shown in the panel, each fitted and centred. `in` / `out` are seconds after the panel opens |
| `background`, `margin`, `slide` | Panel colour, inner margin, slide duration |

## `end_card`

`start` (default `end-3`), and any of `logo` (image), `brand`, `lead`, `headline`, `tagline`. `lead_size` and
`headline_size` adjust the two large rows.

## `theme`

Colours: `background`, `ink`, `paper`, `text`, `muted`, `accent`, `accent2`. Fonts: `fonts.body` and
`fonts.display`, each `{family, files: [{path, weight, style}]}`; the files are copied into the HyperFrames project.
Without fonts the CSS asks for Helvetica/Arial, which HyperFrames replaces with its bundled Inter so renders stay the same on every machine.

## `enhance` (top level) and `render`

`enhance`: defaults for all shots (`face`, `upscale`) plus `workers` (4), `crf` (13), `keep_frames`.
`render`: `crf` (12), `share_crf` (also write a smaller copy at that quality), `strict` (stop when
`hyperframes check` reports problems).
