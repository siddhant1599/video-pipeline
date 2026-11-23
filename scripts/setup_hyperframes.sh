#!/usr/bin/env bash
# HyperFrames needs Node.js 22+ and FFmpeg; it is run through npx, so there is nothing to install here
# beyond checking those and letting it fetch its headless browser.
set -euo pipefail
command -v ffmpeg >/dev/null || { echo "FFmpeg is missing: install it first (apt install ffmpeg / brew install ffmpeg)"; exit 1; }
command -v node >/dev/null || { echo "Node.js is missing: install Node.js 22 or newer (https://nodejs.org)"; exit 1; }
major="$(node -p 'process.versions.node.split(".")[0]')"
[ "$major" -ge 22 ] || { echo "Node.js $major found; HyperFrames needs 22 or newer"; exit 1; }
ver="${HYPERFRAMES_VERSION:-0.9.70}"
npx --yes "hyperframes@$ver" browser ensure
npx --yes "hyperframes@$ver" doctor || true
echo "HyperFrames $ver is ready (run through: npx hyperframes@$ver)"
