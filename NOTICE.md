# Third-party software and models

This repository contains only its own code. The setup scripts download the following at install time; none of it is
redistributed here. Each has its own licence, and some model weights are restricted to non-commercial use. Read the
upstream licence before using the output commercially.

| Component | Used by | Upstream |
|---|---|---|
| HyperFrames | `compose`, `render` | https://github.com/heygen-com/hyperframes |
| GSAP | generated compositions (loaded by HyperFrames projects) | https://gsap.com |
| FFmpeg | every stage | https://ffmpeg.org |
| Demucs | `ingest` (speech/music separation) | https://github.com/facebookresearch/demucs |
| LaMa via simple-lama-inpainting | `clean` | https://github.com/advimman/lama |
| Wan 2.2 image-to-video (hosted Space) | `generate` | https://github.com/Wan-Video/Wan2.2 |
| RIFE 4.26 via ccvfi | `smooth` | https://github.com/hzwer/Practical-RIFE |
| Chatterbox | `voice` | https://github.com/resemble-ai/chatterbox |
| faster-whisper | `transcribe` | https://github.com/SYSTRAN/faster-whisper |
| LatentSync | `lipsync` | https://github.com/bytedance/LatentSync |
| SyncNet (as shipped with LatentSync) | `score` | https://github.com/joonson/syncnet_python |
| Real-ESRGAN (`realesr-general-x4v3`) via spandrel | `enhance` | https://github.com/xinntao/Real-ESRGAN |
| GFPGAN 1.4 via spandrel, facexlib | `enhance` | https://github.com/TencentARC/GFPGAN |

`video_pipeline/vendor/latentsync_runner.py` is a runner written for this project that calls LatentSync's public pipeline;
`video_pipeline/vendor/patch_latentsync.py` applies four small text patches to a LatentSync checkout so it runs without a GPU.

This repository itself has no licence file yet. Until one is added, default copyright applies and others may not
reuse the code.
