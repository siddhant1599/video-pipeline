"""Runs LatentSync on one clip and writes lossless PNG frames.

Run from inside the LatentSync checkout (its `configs/` and `checkpoints/` are
read relative to the working folder) with the lipsync environment:

    python latentsync_runner.py <video_25fps.mp4> <audio.wav> <out_frames_dir> [steps] [guidance] [seed]

The video must be 25 fps and a whole number of 16-frame groups long; the
lipsync stage prepares both. LatentSync keeps its scratch files in ./temp, so
run one clip at a time.
"""
import os
import sys

import cv2
import torch
from diffusers import AutoencoderKL, DDIMScheduler
from omegaconf import OmegaConf

sys.path.insert(0, os.getcwd())
import latentsync.pipelines.lipsync_pipeline as lp  # noqa: E402
from latentsync.models.unet import UNet3DConditionModel  # noqa: E402
from latentsync.pipelines.lipsync_pipeline import LipsyncPipeline  # noqa: E402
from latentsync.whisper.audio2feature import Audio2Feature  # noqa: E402

video, audio, outdir = sys.argv[1:4]
steps = int(sys.argv[4]) if len(sys.argv) > 4 else 20
guidance = float(sys.argv[5]) if len(sys.argv) > 5 else 2.0
seed = int(sys.argv[6]) if len(sys.argv) > 6 else 1247
device = "cuda" if torch.cuda.is_available() else "cpu"
if device == "cpu":
    torch.set_num_threads(int(os.environ.get("VIDEO_PIPELINE_THREADS", os.cpu_count() or 4)))

config = OmegaConf.load("configs/unet/second_stage.yaml")
scheduler = DDIMScheduler.from_pretrained("configs")
audio_encoder = Audio2Feature(model_path="checkpoints/whisper/tiny.pt", device=device, num_frames=config.data.num_frames)
vae = AutoencoderKL.from_pretrained("stabilityai/sd-vae-ft-mse", torch_dtype=torch.float32)
vae.config.scaling_factor = 0.18215
vae.config.shift_factor = 0
unet, _ = UNet3DConditionModel.from_pretrained(OmegaConf.to_container(config.model), "checkpoints/latentsync_unet.pt", device="cpu")
unet = unet.to(dtype=torch.float32)
pipe = LipsyncPipeline(vae=vae, audio_encoder=audio_encoder, unet=unet, scheduler=scheduler).to(device)
torch.manual_seed(seed)
os.makedirs(outdir, exist_ok=True)

_write_video = lp.write_video


def write_png(path, frames, fps):
    # keep the frames lossless; the pipeline's own mp4 is only a preview
    for i, f in enumerate(frames):
        cv2.imwrite(f"{outdir}/{i:05d}.png", cv2.cvtColor(f, cv2.COLOR_RGB2BGR))
    print("frames written", len(frames), flush=True)
    _write_video(path, frames, fps)


lp.write_video = write_png
base = outdir.rstrip("/")
pipe(video_path=video, audio_path=audio, video_out_path=base + "_preview.mp4", video_mask_path=base + "_mask.mp4",
     num_frames=config.data.num_frames, num_inference_steps=steps, guidance_scale=guidance, weight_dtype=torch.float32,
     width=config.data.resolution, height=config.data.resolution)
print("LATENTSYNC_DONE", outdir, flush=True)
