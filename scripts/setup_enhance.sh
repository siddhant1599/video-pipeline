#!/usr/bin/env bash
# enhance environment: LaMa text removal, RIFE retiming, Real-ESRGAN upscaling, GFPGAN faces
source "$(dirname "$0")/_common.sh"
py="$(make_env enhance)"
"$py" -m pip install torch torchvision --index-url "$TORCH_INDEX"
"$py" -m pip install -r "$REPO/requirements/enhance.txt"
"$(dirname "$0")/download_models.sh"
echo "enhance environment ready: $py"
