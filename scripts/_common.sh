# Shared by the setup scripts. Usage: source scripts/_common.sh
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
VENVS="${VIDEO_PIPELINE_VENVS:-$REPO/.venvs}"
# TORCH_INDEX picks the PyTorch build: cpu (default), or e.g. https://download.pytorch.org/whl/cu121 for CUDA 12.1
TORCH_INDEX="${TORCH_INDEX:-https://download.pytorch.org/whl/cpu}"

make_env() {  # make_env <name>
  local dir="$VENVS/$1"
  [ -x "$dir/bin/python" ] || "$PYTHON" -m venv "$dir"
  "$dir/bin/python" -m pip install --quiet --upgrade pip wheel
  echo "$dir/bin/python"
}
