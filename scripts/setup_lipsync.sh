#!/usr/bin/env bash
# lipsync environment: LatentSync code + checkpoints (about 3.5 GB) in third_party/LatentSync, patched to run without a GPU.
source "$(dirname "$0")/_common.sh"
py="$(make_env lipsync)"
"$py" -m pip install torch==2.5.1 torchvision==0.20.1 --index-url "$TORCH_INDEX"
"$py" -m pip install -r "$REPO/requirements/lipsync.txt"

dest="${VIDEO_PIPELINE_LATENTSYNC:-$REPO/third_party/LatentSync}"
# LATENTSYNC_REPO / LATENTSYNC_REV: where the code comes from. The default is the snapshot this pipeline was run with.
src_repo="${LATENTSYNC_REPO:-fffiloni/LatentSync}"
src_type="${LATENTSYNC_REPO_TYPE:-space}"
src_rev="${LATENTSYNC_REV:-058d1fbd5e450d527510907a4094b8826cc206a5}"
mkdir -p "$dest"
DEST="$dest" SRC="$src_repo" TYPE="$src_type" REV="$src_rev" "$py" - <<'PY'
import os
from huggingface_hub import hf_hub_download, snapshot_download

dest = os.environ["DEST"]
snapshot_download(os.environ["SRC"], repo_type=os.environ["TYPE"], revision=os.environ["REV"], local_dir=dest,
                  allow_patterns=["latentsync/**", "configs/**", "eval/**", "preprocess/**", "*.py", "*.txt", "LICENSE*"])
for f in ("latentsync_unet.pt", "whisper/tiny.pt", "auxiliary/syncnet_v2.model", "auxiliary/sfd_face.pth"):
    hf_hub_download("ByteDance/LatentSync", f, local_dir=os.path.join(dest, "checkpoints"))
PY
"$py" "$REPO/video_pipeline/vendor/patch_latentsync.py" "$dest"
echo "lipsync environment ready: $py, LatentSync at $dest"
