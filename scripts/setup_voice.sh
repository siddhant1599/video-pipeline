#!/usr/bin/env bash
# voice environment: Chatterbox. The model (about 3 GB) downloads from Hugging Face on first use.
source "$(dirname "$0")/_common.sh"
py="$(make_env voice)"
"$py" -m pip install -r "$REPO/requirements/voice.txt"
echo "voice environment ready: $py"
