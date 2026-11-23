#!/usr/bin/env bash
# Upscaling and face-restoration weights into models/ (about 350 MB). Check each model's licence before commercial use.
source "$(dirname "$0")/_common.sh"
dir="${VIDEO_PIPELINE_MODELS:-$REPO/models}"
mkdir -p "$dir"
get() {  # get <file> <url>
  [ -s "$dir/$1" ] && { echo "have $1"; return; }
  echo "downloading $1"
  curl -fL --retry 3 -o "$dir/$1.part" "$2" && mv "$dir/$1.part" "$dir/$1"
}
get realesr-general-x4v3.pth https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth
get GFPGANv1.4.pth https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth
