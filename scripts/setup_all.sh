#!/usr/bin/env bash
# All four Python environments, the models and the HyperFrames check. Expect 10+ GB of downloads.
set -euo pipefail
here="$(dirname "$0")"
"$here/setup_core.sh"
"$here/setup_voice.sh"
"$here/setup_enhance.sh"
"$here/setup_lipsync.sh"
"$here/setup_hyperframes.sh"
"$here/../bin/video-pipeline" doctor
