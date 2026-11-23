"""Patches a LatentSync checkout so it runs without a GPU and keeps source detail.

    python patch_latentsync.py <LatentSync dir>

Each patch is an exact text replacement; it is skipped when already applied and
fails loudly when the upstream file no longer matches, so a changed upstream
is noticed instead of silently mis-patched.
"""
import sys
from pathlib import Path

PATCHES = [
    # `turtle` needs tkinter, which headless machines do not have; the import is unused
    ("latentsync/models/attention.py", "from turtle import forward\n", ""),
    # the face detector was pinned to CUDA; follow the pipeline's device instead
    ("latentsync/pipelines/lipsync_pipeline.py",
     'self.image_processor = ImageProcessor(height, mask=mask, device="cuda")',
     "self.image_processor = ImageProcessor(height, mask=mask, device=str(device))"),
    # use the same face_alignment detector on CPU as on GPU
    ("latentsync/utils/image_processor.py", 'if device != "cpu":', "if True:  # same detector on CPU and GPU"),
    # the internal 25 fps conversion re-encodes the input; do it near-losslessly
    ("latentsync/utils/util.py", "-r 25 -crf 18 ", "-r 25 -crf 8 "),
]


def main(root: Path) -> int:
    bad = 0
    for rel, old, new in PATCHES:
        f = root / rel
        text = f.read_text()
        if old in text:
            f.write_text(text.replace(old, new, 1))
            print("patched ", rel)
        elif (new and new in text) or (not new and old not in text):
            print("already ", rel)
        else:
            print("MISMATCH", rel, "- upstream changed; check this patch by hand", file=sys.stderr)
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
