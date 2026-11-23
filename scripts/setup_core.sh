#!/usr/bin/env bash
# core environment: the CLI, ingest, generate, mix, transcribe, compose, render
source "$(dirname "$0")/_common.sh"
py="$(make_env core)"
"$py" -m pip install torch torchaudio --index-url "$TORCH_INDEX"
"$py" -m pip install -r "$REPO/requirements/core.txt"
echo "core environment ready: $py"
