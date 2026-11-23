"""Timing, timeline and layout logic. Needs no media, models or GPU: `python -m pytest tests`."""
import textwrap
from pathlib import Path

import pytest

from video_pipeline.config import ConfigError, Project

ROOT = Path(__file__).resolve().parents[1]


def project(tmp_path, text):
    p = tmp_path / "project.yaml"
    p.write_text(textwrap.dedent(text))
    return Project(p)


BASIC = """
    project: {name: t, fps: 24, width: 1920, height: 1080}
    sources:
      a: {path: input/a.mp4}
    shots:
      - {id: one, from: {source: a, start: 1.0, end: 3.0}}
      - {id: two-b, from: {source: a, start_frame: 10, end_frame: 34}}
      - {id: gen, from: {source: a, start: 0, end: 1.5, keep_fps: true}, smooth: {speed: 0.75}}
      - {id: still, image: {path: input/s.png}, seconds: 2}
    timeline: [one, two-b, gen, still]
    tail: 3
"""


def test_example_project_loads():
    pr = Project(ROOT / "examples" / "project.example.yaml")
    assert pr.duration() > 0
    assert len(pr.timeline()) == len(pr.cfg["timeline"])


def test_shot_lengths(tmp_path):
    pr = project(tmp_path, BASIC)
    assert pr.declared_frames("one") == 48
    assert pr.declared_frames("two-b") == 24
    assert pr.declared_frames("gen") == 48  # 1.5 s slowed to 0.75x at 24 fps
    assert pr.declared_frames("still") == 48


def test_timeline_and_duration(tmp_path):
    pr = project(tmp_path, BASIC)
    assert [i["start"] for i in pr.timeline()] == [0.0, 2.0, 3.0, 5.0]
    assert pr.duration() == 10.0


def test_time_expressions(tmp_path):
    pr = project(tmp_path, BASIC)
    assert pr.time(1.5) == 1.5
    assert pr.time("2.25") == 2.25
    assert pr.time("two-b") == 2.0
    assert pr.time("two-b+0.5") == 2.5
    assert pr.time("two-b.end-0.25") == 2.75
    assert pr.time("one.end") == 2.0
    assert pr.time("start+1") == 1.0
    assert pr.time("end-3") == 7.0
    with pytest.raises(ConfigError):
        pr.time("nowhere+1")


def test_absolute_placement(tmp_path):
    pr = project(tmp_path, BASIC.replace("timeline: [one, two-b, gen, still]", "timeline: [one, {shot: still, at: 6}]"))
    assert pr.time("still") == 6.0
    assert pr.duration() == 11.0


@pytest.mark.parametrize("bad", [
    BASIC.replace("timeline: [one, two-b, gen, still]", "timeline: [one, missing]"),
    BASIC.replace("{id: one, from: {source: a, start: 1.0, end: 3.0}}", "{id: one, from: {source: zzz, start: 1.0, end: 3.0}}"),
    BASIC.replace(", smooth: {speed: 0.75}", ""),
])
def test_bad_projects_are_rejected(tmp_path, bad):
    with pytest.raises(ConfigError):
        pr = project(tmp_path, bad)
        pr.validate()
        pr.timeline()


def test_lipsync_segments():
    from video_pipeline.stages.lipsync import segments

    assert segments(40, 96) == [(0, 40)]
    segs = segments(200, 96)
    assert segs[0][0] == 0 and segs[-1][1] == 200
    for (a, b), (c, d) in zip(segs, segs[1:]):
        assert b - a <= 96 and c == b - 16  # neighbours share one 16-frame group
    assert all(b - a <= 96 for a, b in segs)


def test_smooth_positions():
    np = pytest.importorskip("numpy")
    from video_pipeline.stages.smooth import positions, unevenness

    even = np.ones(20)
    p = positions(even, 20, 1.0)
    assert np.allclose(p, np.arange(20), atol=1e-6)  # even motion is left alone

    jerky = np.tile([2.0, 0.5], 10)  # alternating fast and slow steps
    p = positions(jerky, 20, 1.0)
    assert np.all(np.diff(p) > 0) and p[0] == 0 and p[-1] <= 20
    cum = np.concatenate([[0], np.cumsum(jerky)])
    moved = np.diff(np.interp(p, np.arange(21), cum))
    assert unevenness(moved[2:-2]) < 0.5 * unevenness(jerky)

    slow = positions(even, 40, 0.5, equalize=False)
    assert np.allclose(slow, np.arange(40) * 0.5)


def test_caption_grouping():
    from video_pipeline.stages.transcribe import group

    words = [
        {"word": "This", "start": 0.0, "end": 0.4}, {"word": "is", "start": 0.45, "end": 0.7},
        {"word": "line", "start": 0.72, "end": 0.8}, {"word": "one.", "start": 0.82, "end": 1.3},
        {"word": "Then", "start": 1.4, "end": 1.7}, {"word": "comes", "start": 1.75, "end": 2.1},
        {"word": "another", "start": 3.0, "end": 3.4},
    ]
    lines = group(words)
    assert [l["text"] for l in lines] == ["This is line one.", "Then comes", "another"]  # sentence end, pause
    for a, b in zip(lines, lines[1:]):
        assert a["end"] <= b["start"]
    assert all(len(l["text"]) <= 34 for l in group(words * 3, max_chars=34))


def test_caption_markup():
    from video_pipeline.stages.compose import rich

    assert rich("call *now* <b>") == 'call <span class="hl">now</span> &lt;b&gt;'
