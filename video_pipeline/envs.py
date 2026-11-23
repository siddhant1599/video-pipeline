"""Which Python environment each stage runs in.

The model libraries disagree on their dependencies (numpy 1 vs 2, different
torch builds), so the pipeline keeps four small virtual environments under
`.venvs/` and the CLI starts each stage with the right interpreter.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# stage -> (environment, setup script)
STAGES = {
    "ingest": "core",
    "clean": "enhance",
    "generate": "core",
    "smooth": "enhance",
    "voice": "voice",
    "mix": "core",
    "transcribe": "core",
    "lipsync": "lipsync",
    "score": "lipsync",
    "enhance": "enhance",
    "compose": "core",
    "render": "core",
}
ORDER = ["ingest", "clean", "generate", "smooth", "voice", "mix", "transcribe", "lipsync", "enhance", "score", "compose", "render"]


def venv_root() -> Path:
    return Path(os.environ.get("VIDEO_PIPELINE_VENVS", REPO / ".venvs"))


def python_for(env: str) -> Path | None:
    """Interpreter of an environment: $VIDEO_PIPELINE_PY_<ENV>, else .venvs/<env>/bin/python."""
    override = os.environ.get(f"VIDEO_PIPELINE_PY_{env.upper()}")
    if override:
        return Path(override)
    for rel in ("bin/python", "Scripts/python.exe"):
        p = venv_root() / env / rel
        if p.exists():
            return p
    return None


def latentsync_dir() -> Path:
    return Path(os.environ.get("VIDEO_PIPELINE_LATENTSYNC", REPO / "third_party" / "LatentSync"))


def models_dir() -> Path:
    return Path(os.environ.get("VIDEO_PIPELINE_MODELS", REPO / "models"))


def same_interpreter(py: Path) -> bool:
    """True when this process already runs in the environment `py` belongs to."""
    if os.environ.get("VIDEO_PIPELINE_IN_STAGE") == "1":
        return True
    try:
        return Path(sys.prefix).resolve() == Path(py).absolute().parent.parent.resolve()
    except OSError:
        return False
