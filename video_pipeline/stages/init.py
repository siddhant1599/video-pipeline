"""init: create a project folder with a starter project.yaml."""
from __future__ import annotations

import shutil
from pathlib import Path

from ..envs import REPO
from ..util import log

IGNORE = """# everything video-pipeline makes can be rebuilt; inputs are yours to keep or not
work/
output/
hyperframes/
"""


def main(args):
    d = Path(args.dir).resolve()
    target = d / "project.yaml"
    if target.exists():
        raise SystemExit(f"[video-pipeline] error: {target} already exists")
    (d / "input").mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / "examples" / "project.example.yaml", target)
    (d / ".gitignore").write_text(IGNORE)
    log(f"created {target}\n  1. put your footage, images and voice reference in {d / 'input'}\n"
        f"  2. edit project.yaml (every key is explained in docs/config.md)\n  3. video-pipeline status -p {d}")
