"""compose: write the HyperFrames project for the film.

Reads the timeline, captions, overlays, end card and theme from the project
file and writes a self-contained HyperFrames project (default `hyperframes/`):

    index.html                  the cut: one muted <video> per shot + the soundtrack
    compositions/captions.html  subtitle bar
    compositions/overlay-*.html one per overlay (image panel)
    compositions/end-card.html  closing card
    assets/                     copies of the finished shots, the mix, images, fonts

The output is plain HTML/CSS/GSAP; edit it by hand for anything the config
cannot express, but note that `video-pipeline compose` overwrites it.
"""
from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path

import yaml

from ..config import ConfigError, Project
from ..util import log, probe

GSAP = "https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"
THEME = {"background": "#101014", "ink": "#15131f", "paper": "#f6f5ff", "text": "#ffffff", "muted": "#55506b",
         "accent": "#4bd1fb", "accent2": "#6a5cfe"}
FALLBACK = "Helvetica, Arial, sans-serif"


def rich(text: str) -> str:
    """Escape text; `*word*` becomes a highlighted span."""
    return re.sub(r"\*(.+?)\*", r'<span class="hl">\1</span>', html.escape(str(text), quote=False))


def r4(x: float) -> float:
    return round(float(x), 4)


class Composer:
    def __init__(self, pr: Project):
        self.pr = pr
        self.W, self.H = pr.width, pr.height
        self.u = min(self.W, self.H) / 1080  # sizes in the config are for a 1080-line frame
        self.theme = {**THEME, **{k: v for k, v in (pr.cfg.get("theme") or {}).items() if k != "fonts"}}
        self.fonts = (pr.cfg.get("theme") or {}).get("fonts") or {}
        self.total = pr.duration()
        self.assets = pr.hf / "assets"
        self.font_css = ""

    def px(self, v: float) -> int:
        return int(round(float(v) * self.u))

    # ---- assets ------------------------------------------------------------
    def asset(self, src, kind: str, name: str | None = None) -> str:
        src = self.pr.path(src)
        if not src.exists():
            raise ConfigError(f"file not found: {src}")
        dst = self.assets / kind / (name or src.name)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime or dst.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dst)
        return f"assets/{kind}/{dst.name}"

    def family(self, role: str) -> str:
        f = self.fonts.get(role) or self.fonts.get("body")
        return f'"{f["family"]}", {FALLBACK}' if f else FALLBACK

    def load_fonts(self):
        css = []
        for f in self.fonts.values():
            for file in f.get("files") or []:
                url = self.asset(file["path"], "fonts")
                css.append(f'    @font-face {{ font-family: "{f["family"]}"; font-style: {file.get("style", "normal")}; '
                           f'font-weight: {file.get("weight", 400)}; src: url("{url}"); }}')
        self.font_css = "\n".join(css)

    # ---- building blocks ---------------------------------------------------
    def scene(self, cid: str, style: str, body: str, script: str) -> str:
        return f"""<template>
  <style>
{self.font_css}
    #root {{ position: absolute; inset: 0; }}
    .full {{ position: absolute; inset: 0; }}
    .hl {{ color: {self.theme['accent']}; }}
{style}
  </style>
  <div id="root" data-composition-id="{cid}" data-width="{self.W}" data-height="{self.H}">
{body}
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
{script}
    window.__timelines["{cid}"] = tl;
  </script>
</template>
"""

    def host(self, cid: str, start: float, dur: float, z: int, kind: str = "") -> str:
        kind = f' data-track-kind="{kind}"' if kind else ""
        return (f'      <div id="{cid}" class="scene" data-composition-id="{cid}" data-composition-src="compositions/{cid}.html" '
                f'data-start="{r4(start)}" data-duration="{r4(dur)}" data-track-index="1"{kind} data-width="{self.W}" data-height="{self.H}" '
                f'style="z-index: {z}"></div>')

    # ---- overlays ----------------------------------------------------------
    def panels(self) -> list[dict]:
        out = []
        for i, o in enumerate(self.pr.cfg.get("overlays") or []):
            if o.get("type", "panel") != "panel":
                raise ConfigError(f"overlay {i}: unknown type '{o.get('type')}' (supported: panel)")
            side = o.get("side", "right")
            if side not in ("left", "right", "top", "bottom"):
                raise ConfigError(f"overlay {i}: side must be left, right, top or bottom")
            horizontal = side in ("left", "right")
            size = self.px(o.get("size", 800 if horizontal else 560))
            start, end = self.pr.time(o["start"]), self.pr.time(o["end"])
            w, h = (size, self.H) if horizontal else (self.W, size)
            x = self.W - w if side == "right" else 0
            y = self.H - h if side == "bottom" else 0
            out.append(dict(o, id=o.get("id", f"panel{i + 1}"), side=side, horizontal=horizontal, start=start, end=end, x=x, y=y, w=w, h=h,
                            slide=float(o.get("slide", 0.5))))
        return out

    def panel_scene(self, p: dict) -> tuple[str, float]:
        cid = f"overlay-{p['id']}"
        dur = p["end"] - p["start"] + p["slide"]  # stays mounted while it slides away
        margin = self.px(p.get("margin", 28))
        css = [f"    #pn {{ position: absolute; left: {p['x']}px; top: {p['y']}px; width: {p['w']}px; height: {p['h']}px; "
               f"background: {p.get('background', self.theme['paper'])}; box-shadow: 0 0 {self.px(70)}px rgba(0, 0, 0, 0.28); overflow: hidden; }}"]
        body, js = [], []
        axis = "xPercent" if p["horizontal"] else "yPercent"
        off = 104 if p["side"] in ("right", "bottom") else -104
        js.append(f'    tl.fromTo("#pn", {{ {axis}: {off} }}, {{ {axis}: 0, duration: {p["slide"]}, ease: "power3.inOut" }}, 0);')
        images = p.get("images") or []
        for k, im in enumerate(images):
            url = self.asset(im["path"], "images")
            iw, ih = (int(v) for v in probe(self.pr.path(im["path"]), "stream=width,height")[:2])
            scale = min((p["w"] - 2 * margin) / iw, (p["h"] - 2 * margin) / ih)
            if "width" in im:
                scale = self.px(im["width"]) / iw
            w, h = int(round(iw * scale)), int(round(ih * scale))
            css.append(f"    #im{k} {{ position: absolute; left: {(p['w'] - w) // 2}px; top: {(p['h'] - h) // 2}px; width: {w}px; height: {h}px; }}")
            body.append(f'        <img id="im{k}" src="{url}" alt="{html.escape(im.get("alt", ""), quote=True)}" />')
            t_in = float(im.get("in", p["slide"] * 0.75 if k == 0 else 0))
            js.append(f'    tl.fromTo("#im{k}", {{ opacity: 0, y: {self.px(50)} }}, {{ opacity: 1, y: 0, duration: 0.4, ease: "power3.out" }}, {r4(t_in)});')
            if "out" in im:
                js.append(f'    tl.to("#im{k}", {{ opacity: 0, y: {-self.px(40)}, duration: 0.25, ease: "power2.in" }}, {r4(float(im["out"]))});')
        js.append(f'    tl.to("#pn", {{ {axis}: {off}, duration: {p["slide"]}, ease: "power3.inOut" }}, {r4(p["end"] - p["start"])});')
        inner = "\n".join(body)
        body_html = f'    <div id="pn-clip" class="clip full" data-start="0" data-duration="{r4(dur)}">\n      <div id="pn">\n{inner}\n      </div>\n    </div>'
        return self.scene(cid, "\n".join(css), body_html, "\n".join(js)), dur

    # ---- captions ----------------------------------------------------------
    def caption_items(self) -> list[dict]:
        c = self.pr.cfg.get("captions") or {}
        items = c.get("items")
        if not items and c.get("auto"):
            f = self.pr.audio_dir / "captions.suggested.yaml"
            if not f.exists():
                raise ConfigError("captions.auto is set but there are no word timings yet; run `video-pipeline transcribe`")
            items = yaml.safe_load(f.read_text())["captions"]["items"]
        out = []
        for it in items or []:
            a, b = self.pr.time(it["start"]), self.pr.time(it["end"])
            if b <= a:
                raise ConfigError(f"caption '{it['text']}' ends before it starts")
            out.append(dict(it, start=a, end=min(b, self.total)))
        return out

    def free_area(self, t: float, panels: list[dict]) -> tuple[int, int, int, int]:
        """The part of the frame no panel covers at time t (captions are centred in it)."""
        x, y, w, h = 0, 0, self.W, self.H
        for p in panels:
            if p["start"] <= t < p["end"]:
                if p["horizontal"]:
                    w -= p["w"]
                    x += p["w"] if p["side"] == "left" else 0
                else:
                    h -= p["h"]
                    y += p["h"] if p["side"] == "top" else 0
        return x, y, w, h

    def captions_scene(self, items: list[dict], panels: list[dict]) -> str:
        c = self.pr.cfg.get("captions") or {}
        size, bottom = self.px(c.get("size", 62)), self.px(c.get("bottom", 84))
        bar = c.get("bar", "rgba(21, 19, 31, 0.76)")
        css = f"""    .sub {{ position: absolute; display: flex; justify-content: center; align-items: flex-end; padding-bottom: {bottom}px; }}
    .sub-box {{ font-family: {self.family('body')}; font-weight: {c.get('weight', 700)}; font-size: {size}px; line-height: 1.2; color: {self.theme['text']}; background: {bar}; padding: {self.px(16)}px {self.px(36)}px {self.px(18)}px; border-radius: {self.px(20)}px; text-align: center; max-width: 92%; }}"""
        body, js = [], []
        for i, it in enumerate(items):
            x, y, w, h = self.free_area((it["start"] + it["end"]) / 2, panels)
            fs = self.px(it["size"]) if "size" in it else int(round(size * min(1.0, max(0.7, w / self.W + 0.25))))
            body.append(f'    <div id="sb-{i}" class="clip sub" data-start="{r4(it["start"])}" data-duration="{r4(it["end"] - it["start"])}" '
                        f'style="left: {x}px; top: {y}px; width: {w}px; height: {h}px"><div id="sb-{i}-box" class="sub-box" style="font-size: {fs}px">{rich(it["text"])}</div></div>')
            js.append(f'    tl.fromTo("#sb-{i}-box", {{ opacity: 0, y: {self.px(16)} }}, {{ opacity: 1, y: 0, duration: 0.14, ease: "power2.out" }}, {r4(it["start"])});')
        return self.scene("captions", css, "\n".join(body), "\n".join(js))

    # ---- end card ----------------------------------------------------------
    def end_card_scene(self, e: dict, dur: float) -> str:
        t = self.theme
        rows, css, js, at = [], [], [], 0.35
        css.append(f"    #ec {{ position: absolute; inset: 0; background: {e.get('background', t['paper'])}; display: flex; flex-direction: column; "
                   f"align-items: center; justify-content: center; color: {t['ink']}; text-align: center; padding: 0 {self.px(80)}px; }}")
        if e.get("logo") or e.get("brand"):
            logo = f'<img id="ec-logo" src="{self.asset(e["logo"], "images")}" alt="" />' if e.get("logo") else ""
            rows.append(f'        <div id="ec-brand" class="row">{logo}{rich(e.get("brand", ""))}</div>')
            css.append(f"    #ec-brand {{ display: flex; align-items: center; gap: {self.px(22)}px; font-family: {self.family('body')}; font-weight: 700; font-size: {self.px(76)}px; letter-spacing: -0.02em; }}")
            css.append(f"    #ec-logo {{ height: {self.px(96)}px; width: auto; }}")
        if e.get("lead"):
            rows.append(f'        <div id="ec-lead" class="row">{rich(e["lead"])}</div>')
            css.append(f"    #ec-lead {{ font-family: {self.family('display')}; font-size: {self.px(e.get('lead_size', 110))}px; line-height: 1; margin-top: {self.px(56)}px; }}")
        if e.get("headline"):
            rows.append(f'        <div id="ec-headline" class="row">{rich(e["headline"])}</div>')
            css.append(f"    #ec-headline {{ font-family: {self.family('display')}; font-size: {self.px(e.get('headline_size', 220))}px; line-height: 1.08; color: {t['accent2']}; }}")
        if e.get("tagline"):
            rows.append(f'        <div id="ec-tagline" class="row">{rich(e["tagline"])}</div>')
            css.append(f"    #ec-tagline {{ font-family: {self.family('body')}; font-weight: 500; font-size: {self.px(42)}px; color: {t['muted']}; margin-top: {self.px(26)}px; }}")
        js.append('    tl.fromTo("#ec", { yPercent: 100 }, { yPercent: 0, duration: 0.45, ease: "power3.inOut" }, 0.03);')
        for row in re.findall(r'id="(ec-(?:brand|lead|headline|tagline))"', "\n".join(rows)):
            js.append(f'    tl.fromTo("#{row}", {{ opacity: 0, y: {self.px(30)} }}, {{ opacity: 1, y: 0, duration: 0.35, ease: "power3.out" }}, {r4(at)});')
            at += 0.12
        inner = "\n".join(rows)
        body = f'    <div id="ec-clip" class="clip full" data-start="0" data-duration="{r4(dur)}">\n      <div id="ec">\n{inner}\n      </div>\n    </div>'
        return self.scene("end-card", "\n".join(css), body, "\n".join(js))

    # ---- the cut -----------------------------------------------------------
    def build(self):
        pr = self.pr
        pr.hf.mkdir(parents=True, exist_ok=True)
        comp = pr.hf / "compositions"
        comp.mkdir(exist_ok=True)
        for old in comp.glob("*.html"):
            old.unlink()
        self.load_fonts()
        tl = pr.timeline()
        if not tl:
            raise ConfigError("the timeline is empty")
        panels = self.panels()
        videos, hosts, main_js = [], [], []
        for z, item in enumerate(tl, start=1):
            sid = item["shot"]
            src = pr.shot_video(sid)
            if not src.exists():
                raise ConfigError(f"shot '{sid}' has no finished video yet ({src}); run `video-pipeline enhance`")
            url = self.asset(src, "media")
            videos.append(f'      <video id="shot-{sid}" class="clip shot" src="{url}" data-start="{r4(item["start"])}" data-duration="{r4(item["duration"])}" '
                          f'data-track-index="0" style="z-index: {z}" muted playsinline></video>')
        z = len(tl) + 10
        for p in panels:
            text, dur = self.panel_scene(p)
            (comp / f"overlay-{p['id']}.html").write_text(text)
            hosts.append(self.host(f"overlay-{p['id']}", p["start"], min(dur, self.total - p["start"]), z))
            z += 1
            # optionally slide the footage aside so the subject stays in view next to the panel
            if p.get("push_shot"):
                d = self.px(p.get("push", p["w"] / 2 / self.u if p["horizontal"] else p["h"] / 2 / self.u))
                d = -d if p["side"] in ("right", "bottom") else d
                ax = "x" if p["horizontal"] else "y"
                main_js.append(f'      tl.fromTo("#shot-{p["push_shot"]}", {{ {ax}: 0 }}, {{ {ax}: {d}, duration: {p["slide"]}, ease: "power3.inOut" }}, {r4(p["start"])});')
                main_js.append(f'      tl.to("#shot-{p["push_shot"]}", {{ {ax}: 0, duration: {p["slide"]}, ease: "power3.inOut" }}, {r4(p["end"])});')
        e = pr.cfg.get("end_card")
        if e:
            start = pr.time(e.get("start", "end-3"))
            (comp / "end-card.html").write_text(self.end_card_scene(e, self.total - start))
            hosts.append(self.host("end-card", start, self.total - start, z))
            z += 1
        items = self.caption_items()
        if items:
            (comp / "captions.html").write_text(self.captions_scene(items, panels))
            hosts.append(self.host("captions", 0, self.total, z + 10, kind="captions"))
        mix = pr.audio_dir / "mix.wav"
        audio = ""
        if mix.exists():
            audio = (f'      <audio id="mix" src="{self.asset(mix, "media")}" data-start="0" data-duration="{self.total}" '
                     f'data-track-index="2" data-volume="1"></audio>')
        else:
            log("no soundtrack (work/audio/mix.wav); the film will be silent")
        nl = "\n"
        index = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={self.W}, height={self.H}" />
    <script src="{GSAP}"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ margin: 0; width: {self.W}px; height: {self.H}px; overflow: hidden; background: {self.theme['background']}; }}
      #root {{ position: relative; width: {self.W}px; height: {self.H}px; overflow: hidden; }}
      #ground {{ position: absolute; inset: 0; background: {self.theme['background']}; }}
      .shot {{ position: absolute; left: 0; top: 0; width: {self.W}px; height: {self.H}px; object-fit: cover; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{self.total}" data-width="{self.W}" data-height="{self.H}">
      <div id="ground"></div>
{nl.join(videos)}
{nl.join(hosts)}
{audio}
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
{nl.join(main_js)}
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""
        (pr.hf / "index.html").write_text(index)
        ver = (pr.cfg.get("project") or {}).get("hyperframes_version", "0.9.70")
        slug = re.sub(r"[^a-z0-9]+", "-", pr.name.lower()).strip("-") or "film"
        if not (pr.hf / "meta.json").exists():
            (pr.hf / "meta.json").write_text(json.dumps({"id": slug, "name": pr.name}, indent=2) + "\n")
        (pr.hf / "package.json").write_text(json.dumps({"name": slug, "private": True, "type": "module", "scripts": {
            k: f"npx --yes hyperframes@{ver} {k if k != 'dev' else 'preview'}" for k in ("dev", "check", "render")}}, indent=2) + "\n")
        (pr.hf / "hyperframes.json").write_text(json.dumps({
            "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
            "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
            "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
            "media": {"autoProxy": True}}, indent=2) + "\n")
        (pr.hf / "timeline.json").write_text(json.dumps({"duration": self.total, "fps": pr.fps, "shots": tl,
                                                         "captions": [{k: it[k] for k in ("text", "start", "end")} for it in items]}, indent=1))
        log(f"{len(tl)} shot(s), {len(items)} caption(s), {len(panels)} overlay(s){', end card' if e else ''}; {self.total:.2f} s -> {pr.hf}")


def main(args):
    Composer(Project(args.project)).build()
