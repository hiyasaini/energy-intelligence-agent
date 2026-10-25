"""Record the hackathon MVP demo video (under 2 minutes) of the REAL app, with voiceover and motion graphics.

It runs on your machine against the real Streamlit app and a real research run (default NTPC, a NIFTY 50
Track B company), so the video shows the system actually working on public data.

What you get: an animated title card, chapter captions and a progress bar, a moving cursor with click
ripples, spotlights and zooms on the key details, smooth scrolling, fades between scenes, an outro card,
a neural voiceover and burned-in timing for subtitles (demo_video.srt).

Covered, in order: live research start -> Overview dashboard (price, NIFTY 50 benchmark, financials, capacity,
ratios, project map, verdict) -> Research summary / Key metrics / Latest developments / Insights tabs ->
Discovery Feed and Evidence Passport (evidence, calculations, counterargument, falsification, strength) ->
click-through to the source page with the passage highlighted -> all six modules -> Contradiction Lab ->
Discovery Graph -> Promise-to-cash timeline -> Report Studio.

Usage (project folder, inside the virtual environment):
  pip install -r requirements.txt -r requirements-video.txt
  python -m playwright install chromium
  python scripts/make_demo_video.py --company NTPC
Options: --voice en-IN-PrabhatNeural (male) · --run-id <id> · --show (watch the browser) · --out file.mp4
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import importlib.util
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
W, H = 1920, 1080          # output video size
VW, VH = 1536, 864         # browser viewport, drawn at 125% so text stays readable in the video
MAX_SECONDS = 118          # the brief allows up to 2 minutes
GAP = 0.45                 # breath between narrated scenes
WORDS_PER_SEC = 2.3        # calm speaking pace for your own voiceover (about 140 words a minute)


# ------------------------------------------------------------------------------------------------
# The film: narration + what happens on screen while it is spoken
# ------------------------------------------------------------------------------------------------

@dataclass
class Scene:
    key: str
    chapter: str
    sub: str
    text: str
    page: str | None = None                 # page slug to open (fade transition) before the scene starts
    steps: list = field(default_factory=list)


def film(company: str) -> list[Scene]:
    return [
        Scene("intro", "", "",
              "Meet the Energy Intelligence Agent, our Track B entry for ATMOS 2026. It is not a chatbot or a "
              "summariser. It researches any listed energy company on its own, forms hypotheses, and then tries "
              "to disprove them.",
              None, [("title",)]),
        Scene("search", "Autonomous research", "Any listed energy company, no company-specific code",
              f"We enter a NIFTY 50 company, {company}. The agent reads NSE annual reports, filings and market "
              "data by itself.",
              None, [("search", company), ("spot", ".st-key-panel_job", 3.2)]),
        Scene("dashboard", "Overview dashboard", "Every figure from a cited filing or calculated in code",
              "In a finished run, the dashboard shows the price and NIFTY 50 benchmark, financials from the "
              "filings, capacity, balance-sheet ratios and the agent's verdict.",
              "overview", [("spot", "[class*='st-key-panel_hdr']", 2.6), ("click_text", "5Y", 1.4),
                           ("spot", ".st-key-panel_fin", 2.2), ("scroll", 430), ("spot", ".st-key-panel_ratios", 1.8),
                           ("spot", ".st-key-panel_verdict", 1.6)]),
        Scene("tabs", "Research summary", "Key metrics · Latest developments · Insights",
              "Other tabs give a research summary, key metrics, the latest developments and insights.",
              None, [("top",), ("tab", "Research summary", 1.9), ("tab", "Key metrics", 1.9),
                     ("tab", "Latest developments", 1.9), ("tab", "Insights", 1.9)]),
        Scene("feed", "Discovery Feed & Evidence Passport", "The discovery, why it matters, and the proof",
              "The Discovery Feed ranks the findings. Each Evidence Passport shows the exact passages, the "
              "calculations, the strongest counterargument, a falsification condition and the evidence strength.",
              "discovery-feed", [("spot", "first:.eia-find", 2.0), ("click_text", "Open Evidence Passport", 1.2),
                                 ("zoom", "first:.eia-quote", 1.3, 2.6), ("tab", "Calculations", 1.8),
                                 ("tab", "Challenge and limits", 2.4)]),
        Scene("source", "Click through to the source", "Original document, cited page, passage highlighted",
              "One click opens the original filing at the cited page, with the passage highlighted.",
              None, [("tab", "Supporting evidence", 0.6), ("click_text", "View page in document", 2.2),
                     ("mark", 2.6)]),
        Scene("modules", "Six analytical modules", "Deterministic calculations linked to their input facts",
              "Six modules run on every company: Promise versus Reality, Green Growth, Capital and Cash, Hidden "
              "Risk, Hidden Connections and Early Warning.",
              "promise-vs-reality", [("wait", 1.3), ("nav", "green-growth", 1.3), ("nav", "capital-cash", 1.3),
                                     ("nav", "hidden-risk", 1.3), ("nav", "hidden-connections", 1.3),
                                     ("nav", "early-warning", 1.3)]),
        Scene("contradictions", "Self-falsification", "Counter-evidence search over up to three rounds",
              "The agent searches for counter-evidence. Where sources disagree, findings stay unresolved instead "
              "of being overstated.",
              "contradiction-lab", [("spot", ".eia-stat", 2.4), ("scroll", 380)]),
        Scene("graph", "Discovery Graph", "Source → fact → calculation → finding",
              "The Discovery Graph traces each finding back to its sources.",
              "discovery-graph", [("zoom", ".st-key-panel_graphfull", 1.18, 3.4)]),
        Scene("timeline", "Promise-to-cash timeline", "When the story changed",
              "The timeline shows when targets were set, and what was later delivered.",
              "timeline", [("spot", ".st-key-panel_tlchart", 3.0)]),
        Scene("report", "Report Studio", "Markdown and HTML reports with clickable sources",
              "Report Studio exports the full report with source links. The same agent works for any listed "
              "energy company.",
              "report-studio", [("hover_text", "Download HTML report", 2.2), ("outro",)]),
    ]


# ------------------------------------------------------------------------------------------------
# Motion-graphics layer injected into the page (idempotent; survives Streamlit reruns)
# ------------------------------------------------------------------------------------------------

FX_JS = r"""
() => {
  if (window.fx) return;
  const css = `
  #fx-cursor{position:fixed;left:0;top:0;width:26px;height:26px;z-index:2147483004;pointer-events:none;
    transition:transform .75s cubic-bezier(.22,.9,.25,1);transform:translate(70vw,60vh)}
  #fx-cursor svg{filter:drop-shadow(0 2px 6px rgba(0,0,0,.6))}
  .fx-ripple{position:fixed;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;z-index:2147483002;
    border:2px solid #22C7E8;pointer-events:none;animation:fxr .7s ease-out forwards}
  @keyframes fxr{from{transform:scale(.4);opacity:1}to{transform:scale(4);opacity:0}}
  #fx-spot{position:fixed;z-index:2147483001;pointer-events:none;border-radius:14px;opacity:0;
    box-shadow:0 0 0 3px #22C7E8,0 0 30px 6px rgba(34,199,232,.45),0 0 0 200vmax rgba(3,8,18,.62);
    transition:all .6s cubic-bezier(.22,.9,.25,1)}
  #fx-chap{position:fixed;left:300px;bottom:30px;z-index:2147483003;pointer-events:none;font-family:Inter,'Segoe UI',sans-serif;
    max-width:min(640px,60vw);transform:translateY(26px);opacity:0;transition:transform .7s cubic-bezier(.22,.9,.25,1),opacity .5s}
  #fx-chap.on{transform:none;opacity:1}
  #fx-chap .box{background:rgba(7,13,26,.92);border:1px solid #1E2D48;border-left:4px solid #22C7E8;border-radius:12px;
    padding:12px 20px 13px;box-shadow:0 10px 30px rgba(0,0,0,.45);backdrop-filter:blur(6px)}
  #fx-chap .n{color:#22C7E8;font-size:12px;font-weight:800;letter-spacing:.22em}
  #fx-chap .t{color:#fff;font-size:24px;font-weight:800;margin-top:2px}
  #fx-chap .s{color:#93A4BE;font-size:14px;margin-top:2px}
  #fx-bar{position:fixed;left:0;right:0;top:0;height:4px;z-index:2147483003;display:flex;gap:3px;padding:0 3px;
    pointer-events:none}
  #fx-bar i{flex:1;background:rgba(147,164,190,.18);border-radius:2px;transition:background .6s}
  #fx-bar i.done{background:#1E6F86} #fx-bar i.cur{background:#22C7E8}
  #fx-veil{position:fixed;inset:0;background:#070D1A;z-index:2147483000;opacity:0;pointer-events:none;transition:opacity .45s}
  #fx-card{position:fixed;inset:0;z-index:2147483005;display:flex;flex-direction:column;align-items:center;justify-content:center;
    text-align:center;font-family:Inter,'Segoe UI',sans-serif;color:#E6EDF7;transition:opacity .8s;
    background:radial-gradient(1200px 700px at 50% 38%,#11284A 0%,#070D1A 62%)}
  #fx-card .grid{position:absolute;inset:0;opacity:.18;background-image:linear-gradient(#22C7E833 1px,transparent 1px),
    linear-gradient(90deg,#22C7E833 1px,transparent 1px);background-size:56px 56px;
    mask-image:radial-gradient(circle at 50% 45%,#000 0%,transparent 70%);animation:fxg 14s linear infinite}
  @keyframes fxg{to{background-position:56px 56px}}
  #fx-card .up{opacity:0;transform:translateY(22px);animation:fxu .9s cubic-bezier(.22,.9,.25,1) forwards}
  @keyframes fxu{to{opacity:1;transform:none}}
  #fx-card .k{font-size:15px;font-weight:800;letter-spacing:.34em;color:#22C7E8}
  #fx-card .h{font-size:68px;font-weight:900;margin:16px 0 8px;letter-spacing:-.01em;
    background:linear-gradient(90deg,#fff 0%,#9BE7F7 50%,#fff 100%);-webkit-background-clip:text;color:transparent;
    background-size:200% 100%;animation:fxu .9s .15s cubic-bezier(.22,.9,.25,1) forwards,fxs 4s 1s linear infinite}
  @keyframes fxs{to{background-position:-200% 0}}
  #fx-card .p{font-size:22px;color:#93A4BE}
  #fx-card .chips{display:flex;gap:12px;margin-top:38px}
  #fx-card .chips span{padding:9px 16px;border:1px solid #24406A;border-radius:999px;background:#0C1A30;font-size:15px;
    color:#CFE3F5}
  #fx-card .line{height:2px;width:0;background:linear-gradient(90deg,transparent,#22C7E8,transparent);margin-top:34px;
    animation:fxl 1.4s .8s ease forwards}
  @keyframes fxl{to{width:520px}}
  #fx-card .f{margin-top:16px;font-size:14px;color:#62748F}
  .fx-zoom{transition:transform 1.1s cubic-bezier(.22,.9,.25,1)!important}`;
  const st = document.createElement('style'); st.id = 'fx-style'; st.textContent = css; document.head.appendChild(st);
  const mk = (id, html) => { const d = document.createElement('div'); d.id = id; d.innerHTML = html || '';
    document.documentElement.appendChild(d); return d; };
  mk('fx-cursor', '<svg width="26" height="26" viewBox="0 0 24 24"><path d="M4 2l15 9-6.5 1.6L9.6 19z" fill="#fff" ' +
     'stroke="#070D1A" stroke-width="1.4" stroke-linejoin="round"/></svg>');
  mk('fx-spot'); mk('fx-chap'); mk('fx-bar'); mk('fx-veil');
  const app = () => document.querySelector('[data-testid="stMain"]') || document.querySelector('section.main') ||
                    document.querySelector('[data-testid="stAppViewContainer"]');
  const scroller = () => {
    const c = ['[data-testid="stMain"]', 'section.main', '[data-testid="stAppViewContainer"]',
               '[data-testid="stAppViewBlockContainer"]'];
    for (const s of c) { const e = document.querySelector(s); if (e && e.scrollHeight > e.clientHeight + 5) return e; }
    return document.scrollingElement;
  };
  const union = (sel) => { let one = false; if (sel.startsWith('first:')) { one = true; sel = sel.slice(6); }
    let r = [...document.querySelectorAll(sel)].map(e => e.getBoundingClientRect())
      .filter(b => b.width > 4 && b.height > 4 && b.bottom > 0 && b.top < innerHeight);
    if (one) r = r.slice(0, 1);
    if (!r.length) return null;
    const x = Math.min(...r.map(b => b.left)), y = Math.min(...r.map(b => b.top));
    return {x, y, w: Math.max(...r.map(b => b.right)) - x, h: Math.max(...r.map(b => b.bottom)) - y}; };
  window.fx = {
    cursor(x, y) { document.getElementById('fx-cursor').style.transform = `translate(${x}px,${y}px)`; },
    ripple(x, y) { const d = document.createElement('div'); d.className = 'fx-ripple'; d.style.left = x + 'px';
      d.style.top = y + 'px'; document.documentElement.appendChild(d); setTimeout(() => d.remove(), 800); },
    rect(sel) { return union(sel); },
    spot(sel, pad = 10) { const s = document.getElementById('fx-spot'); const r = sel ? union(sel) : null;
      if (!r) { s.style.opacity = 0; return false; }
      Object.assign(s.style, {left: (r.x - pad) + 'px', top: (r.y - pad) + 'px', width: (r.w + 2 * pad) + 'px',
        height: (r.h + 2 * pad) + 'px', opacity: 1}); return true; },
    reveal(sel) { const e = document.querySelector(sel.replace(/^first:/, '')); if (!e) return false;
      const b = e.getBoundingClientRect(); if (b.top < 70 || b.bottom > innerHeight - 40) {
        scroller().scrollBy({top: b.top - innerHeight * 0.28, behavior: 'smooth'}); } return true; },
    scroll(dy) { scroller().scrollBy({top: dy, behavior: 'smooth'}); },
    top() { const s = scroller(); s.scrollTo({top: 0, behavior: 'smooth'}); },
    zoom(sel, k) { const a = app(); if (!a) return; a.classList.add('fx-zoom');
      if (!sel || k === 1) { a.style.transform = ''; setTimeout(() => { a.style.zIndex = ''; a.style.background = ''; }, 1150); return; }
      if (getComputedStyle(a).position === 'static') a.style.position = 'relative';
      a.style.zIndex = '999995'; a.style.background = '#070D1A';  /* above Streamlit's sidebar while zoomed, so nothing slides under it */
      const r = union(sel); if (!r) return; const o = a.getBoundingClientRect();
      a.style.transformOrigin = `${r.x - o.left + r.w / 2}px ${r.y - o.top + r.h / 2}px`;
      a.style.transform = `scale(${k})`; },
    chapter(n, total, t, s) { const c = document.getElementById('fx-chap');
      const sb = document.querySelector('section[data-testid="stSidebar"]');
      const sbw = sb && sb.getAttribute('aria-expanded') !== 'false' ? sb.getBoundingClientRect().right : 0;
      c.style.left = Math.max(24, sbw + 24) + 'px';
      if (!t) { c.classList.remove('on'); return; }
      c.classList.remove('on'); setTimeout(() => { c.innerHTML = `<div class="box"><div class="n">${String(n).padStart(2,'0')} / ${String(total).padStart(2,'0')}</div>` +
        `<div class="t">${t}</div><div class="s">${s}</div></div>`; c.classList.add('on'); }, 250); },
    bar(i, n) { const b = document.getElementById('fx-bar'); if (b.children.length !== n) b.innerHTML = '<i></i>'.repeat(n);
      [...b.children].forEach((e, k) => e.className = k < i ? 'done' : k === i ? 'cur' : ''); },
    veil(on) { document.getElementById('fx-veil').style.opacity = on ? 1 : 0; },
    card(html) { let c = document.getElementById('fx-card');
      if (!html) { if (c) { c.style.opacity = 0; setTimeout(() => c.remove(), 850); } return; }
      if (!c) c = mk('fx-card'); c.style.opacity = 1; c.innerHTML = '<div class="grid"></div>' + html; },
    mark() { const m = document.querySelector('.eia-doc mark'); if (!m) return null;
      m.scrollIntoView({block: 'center', behavior: 'smooth'}); return true; },
  };
}
"""


def title_card(company: str) -> str:
    chips = "".join(f"<span class='up' style='animation-delay:{.9 + i * .12:.2f}s'>{w}</span>" for i, w in
                    enumerate(["Discover", "Connect", "Calculate", "Reason", "Challenge", "Prove"]))
    return ("<div class='k up'>ATMOS 2026 · FINDING THE NEXT SIGNAL · TRACK B</div>"
            "<div class='h'>Energy Intelligence Agent</div>"
            "<div class='p up' style='animation-delay:.35s'>Autonomous, evidence-backed research on listed Indian "
            "energy companies</div>"
            f"<div class='chips'>{chips}</div><div class='line'></div>"
            f"<div class='f up' style='animation-delay:1.7s'>MVP demo · live run on {company} (NIFTY 50)</div>")


def outro_card() -> str:
    items = ["Live public sources", "Six modules", "Counter-evidence search", "Evidence Passport",
             "Falsification conditions", "Source click-through"]
    chips = "".join(f"<span class='up' style='animation-delay:{.4 + i * .1:.2f}s'>✓ {w}</span>" for i, w in
                    enumerate(items))
    return ("<div class='h' style='font-size:58px'>Energy Intelligence Agent</div>"
            "<div class='p up' style='animation-delay:.2s'>Every claim traceable to its source</div>"
            f"<div class='chips' style='flex-wrap:wrap;justify-content:center;max-width:1000px'>{chips}</div>"
            "<div class='line'></div><div class='k up' style='margin-top:18px;animation-delay:1.2s'>"
            "ATMOS 2026 · TRACK B · ENERGY, POWER &amp; RENEWABLES</div>")


# ------------------------------------------------------------------------------------------------
# Browser choreography
# ------------------------------------------------------------------------------------------------

class Director:
    def __init__(self, page, base: str, run_id: str):
        self.p, self.base, self.run_id = page, base, run_id

    def ensure_fx(self):
        self.p.evaluate(FX_JS)

    def wait(self, s: float):
        self.p.wait_for_timeout(int(s * 1000))

    def move(self, x: float, y: float, settle: float = 0.8):
        self.ensure_fx()
        self.p.evaluate("([x, y]) => fx.cursor(x, y)", [x, y])
        self.wait(settle)

    def click_locator(self, loc, after: float = 1.0):
        loc.scroll_into_view_if_needed(timeout=4000)
        b = loc.bounding_box()
        if b:
            x, y = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
            self.move(x, y)
            self.p.evaluate("([x, y]) => fx.ripple(x, y)", [x, y])
        loc.click(timeout=4000)
        self.wait(after)

    def spot(self, sel: str, secs: float):
        self.ensure_fx()
        if not self.p.evaluate("(s) => fx.reveal(s)", sel):
            return
        self.wait(0.55)
        r = self.p.evaluate("(s) => fx.rect(s)", sel)
        if r:
            self.move(r["x"] + r["w"] * 0.82, r["y"] + min(r["h"] * 0.5, 120), 0.2)
        self.p.evaluate("(s) => fx.spot(s)", sel)
        self.wait(secs)
        self.p.evaluate("() => fx.spot(null)")
        self.wait(0.35)

    def zoom(self, sel: str, k: float, secs: float):
        self.ensure_fx()
        if not self.p.evaluate("(s) => fx.reveal(s)", sel):
            return
        self.wait(0.6)
        self.p.evaluate("([s, k]) => fx.zoom(s, k)", [sel, k])
        self.wait(secs)
        self.p.evaluate("() => fx.zoom(null, 1)")
        self.wait(0.9)

    def nav(self, slug: str, fade: bool = True):
        self.ensure_fx()
        if fade:
            self.p.evaluate("() => fx.veil(true)")
            self.wait(0.45)
        try:
            self.p.locator(f".st-key-nav_{slug} button").first.click(timeout=4000)
        except Exception:  # sidebar hidden or another Streamlit build: deep link instead
            self.p.goto(f"{self.base}/?page={slug}&run={self.run_id}")
            self.p.wait_for_selector(".st-key-nav_overview", timeout=60000)
        self.wait(2.4)
        self.ensure_fx()
        self.p.evaluate("() => { const s = document.querySelector('[data-testid=\"stMain\"], section.main');"
                        " if (s) s.scrollTo(0, 0); window.scrollTo(0, 0); }")

    def step(self, st: tuple, company: str):
        kind, *a = st
        p = self.p
        if kind == "wait":
            self.wait(a[0])
        elif kind == "title":
            self.wait(0.2)
        elif kind == "search":
            box = p.get_by_placeholder(re.compile("Search company", re.I)).first
            self.click_locator(box, 0.3)
            box.fill("")
            box.type(a[0], delay=130)
            self.wait(0.4)
            box.press("Enter")
            self.wait(4.5)
        elif kind == "spot":
            self.spot(a[0], a[1])
        elif kind == "zoom":
            self.zoom(a[0], a[1], a[2])
        elif kind == "scroll":
            self.ensure_fx()
            self.move(VW * 0.62, VH * 0.62, 0.15)
            p.evaluate("(d) => fx.scroll(d)", a[0])
            self.wait(1.1)
        elif kind == "top":
            self.ensure_fx()
            p.evaluate("() => fx.top()")
            self.wait(0.9)
        elif kind == "click_text":
            self.click_locator(p.get_by_text(a[0], exact=True).first, a[1])
        elif kind == "hover_text":
            loc = p.get_by_text(a[0], exact=True).first
            loc.scroll_into_view_if_needed(timeout=4000)
            b = loc.bounding_box()
            if b:
                self.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
            loc.hover()
            self.wait(a[1])
        elif kind == "tab":
            self.click_locator(p.get_by_role("tab", name=re.compile("^" + re.escape(a[0]))).first, a[1])
        elif kind == "nav":
            self.nav(a[0], fade=False)
            self.wait(a[1])
        elif kind == "mark":
            self.ensure_fx()
            if p.evaluate("() => fx.mark()"):
                self.wait(0.8)
                self.spot(".eia-doc mark", a[0])
        elif kind == "outro":
            self.wait(0.4)
            p.evaluate("() => { fx.chapter(0, 0, ''); fx.spot(null); }")
            p.evaluate("(h) => fx.card(h)", outro_card())
            self.wait(4.6)


# ------------------------------------------------------------------------------------------------
# Voice, capture and assembly
# ------------------------------------------------------------------------------------------------

def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_ff(args: list[str]) -> str:
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-y", *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg failed:\n" + p.stderr[-2000:])
    return p.stderr


def media_duration(path: Path) -> float:
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", p.stderr)
    if not m:
        raise RuntimeError(f"cannot read duration of {path}")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def speak(text: str, out: Path, voice: str, rate: str) -> Path:
    """Microsoft neural voice via edge-tts (internet); offline fallback is the system voice (pyttsx3)."""
    try:
        import edge_tts

        async def go():
            await edge_tts.Communicate(text, voice, rate=rate).save(str(out.with_suffix(".mp3")))
        asyncio.run(go())
        return out.with_suffix(".mp3")
    except Exception as e:
        print(f"   neural voice unavailable ({type(e).__name__}); using the offline system voice")
        import pyttsx3
        eng = pyttsx3.init()
        eng.setProperty("rate", 178)
        eng.save_to_file(text, str(out.with_suffix(".wav")))
        eng.runAndWait()
        return out.with_suffix(".wav")


def voiceover(scenes: list[Scene], work: Path, voice: str) -> tuple[list[Path], list[float]]:
    rate = 6
    for attempt in range(3):
        clips, lens = [], []
        for i, s in enumerate(scenes):
            c = speak(s.text, work / f"vo{i:02d}_{s.key}", voice, f"+{rate}%")
            clips.append(c)
            lens.append(media_duration(c))
        total = sum(lens) + GAP * len(scenes) + 8  # + room for actions that run past the voice
        print(f"   narration {sum(lens):.0f}s at +{rate}% (estimated video {total:.0f}s)")
        if total <= MAX_SECONDS or attempt == 2:
            return clips, lens
        rate += int((total / MAX_SECONDS - 1) * 100) + 3
        print(f"   too long for 2 minutes: speeding the voice up to +{rate}%")
    return clips, lens


class Recorder:
    """Chrome DevTools screencast: sharp JPEG frames with timestamps."""

    def __init__(self, page, frames_dir: Path):
        self.dir = frames_dir
        self.frames: list[tuple[float, Path]] = []
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._on_frame)
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": W, "maxHeight": H,
                                               "everyNthFrame": 1})

    def _on_frame(self, ev):
        p = self.dir / f"f{len(self.frames):06d}.jpg"
        p.write_bytes(base64.b64decode(ev["data"]))
        self.frames.append((time.time(), p))  # same clock as the scene timings, so cuts land exactly
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
        except Exception:
            pass

    def stop(self):
        try:
            self.cdp.send("Page.stopScreencast")
        except Exception:
            pass


def build_video(frames, spans, out: Path, work: Path) -> None:
    """Keep only the frames inside each scene (page loads between scenes are cut)."""
    lines, last = [], None
    for t0, t1 in spans:
        inside = [(t, p) for t, p in frames if t0 < t < t1]
        before = [(t, p) for t, p in frames if t <= t0]
        first = before[-1][1] if before else (inside[0][1] if inside else last)
        if first is None:
            continue
        seq = [(t0, first)] + inside
        for i, (t, p) in enumerate(seq):
            nxt = seq[i + 1][0] if i + 1 < len(seq) else t1
            lines.append(f"file '{p.resolve().as_posix()}'\nduration {max(0.001, nxt - t):.4f}")
            last = p
    lines.append(f"file '{last.resolve().as_posix()}'")
    lst = work / "frames.txt"
    lst.write_text("\n".join(lines), encoding="utf-8")
    run_ff(["-f", "concat", "-safe", "0", "-i", str(lst), "-vf",
            f"fps=30,scale={W}:{H}:flags=lanczos,format=yuv420p,fade=t=in:st=0:d=0.6",
            "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-tune", "animation", str(out)])


def build_audio(clips, lengths, out: Path, work: Path, music: Path | None) -> None:
    padded = []
    for i, (c, L) in enumerate(zip(clips, lengths)):
        p = work / f"pad{i:02d}.wav"
        run_ff(["-i", str(c), "-af", f"adelay=150|150,apad=whole_dur={L:.3f},atrim=0:{L:.3f}", "-ar", "48000", "-ac", "2",
                str(p)])
        padded.append(p)
    lst = work / "audio.txt"
    lst.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in padded), encoding="utf-8")
    voice = work / "voice_only.wav"
    run_ff(["-f", "concat", "-safe", "0", "-i", str(lst), "-c:a", "pcm_s16le", str(voice)])
    if music and music.exists():  # optional background music, ducked under the voice
        total = sum(lengths)
        run_ff(["-i", str(voice), "-stream_loop", "-1", "-i", str(music), "-filter_complex",
                f"[1:a]volume=0.10,atrim=0:{total:.2f},afade=t=in:d=1.5,afade=t=out:st={max(0, total - 2.5):.2f}:d=2.5[m];"
                "[0:a][m]amix=inputs=2:duration=first:normalize=0[a]", "-map", "[a]", "-ar", "48000", str(out)])
    else:
        shutil.copy(voice, out)


def write_srt(scenes, lengths, out: Path) -> None:
    def ts(x):
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    t, rows = 0.0, []
    for i, (s, L) in enumerate(zip(scenes, lengths), 1):
        rows.append(f"{i}\n{ts(t + 0.2)} --> {ts(t + L - 0.25)}\n{s.text}\n")
        t += L
    out.write_text("\n".join(rows), encoding="utf-8")


# ------------------------------------------------------------------------------------------------
# App and data
# ------------------------------------------------------------------------------------------------

def latest_run(db: Path, company: str) -> str | None:
    if not db.exists():
        return None
    con = sqlite3.connect(db)
    q = company.strip().lower()
    for rid, cj in con.execute("SELECT id, company_json FROM runs WHERE mode != 'demo' AND status IN "
                               "('completed', 'partial') ORDER BY started_at DESC"):
        c = json.loads(cj)
        names = [str(c.get("name", "")).lower(), str(c.get("nse", "")).lower()]
        if any(n and (q == n or q in n) for n in names):
            if con.execute("SELECT COUNT(*) FROM hypotheses WHERE run_id=?", (rid,)).fetchone()[0]:
                return rid
    return None


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_app(port: int) -> subprocess.Popen:
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"), "--server.headless", "true",
                             "--server.port", str(port), "--browser.gatherUsageStats", "false"],
                            cwd=ROOT, env={**os.environ, "PYTHONUTF8": "1"},
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(90):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=2)
            return proc
        except Exception:
            time.sleep(1)
    proc.terminate()
    sys.exit("The app did not start. Run  python -m streamlit run app.py  to see the error.")


# ------------------------------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--company", default="NTPC", help="NIFTY 50 Track B company (default NTPC)")
    ap.add_argument("--run-id", default=None, help="use this research run instead of the latest one")
    ap.add_argument("--tts", action="store_true", help="also add a synthetic voice (default: silent video for your own voice)")
    ap.add_argument("--voice", default="en-IN-NeerjaNeural", help="synthetic voice for --tts")
    ap.add_argument("--music", default=None, help="optional background music file (mp3/wav), mixed quietly")
    ap.add_argument("--out", default=str(ROOT / "demo_video.mp4"))
    ap.add_argument("--show", action="store_true", help="show the browser window while recording")
    a = ap.parse_args()

    need = ["pydantic", "streamlit", "plotly", "fitz", "playwright", "imageio_ffmpeg"] + (["edge_tts"] if a.tts else [])
    missing = [m for m in need if importlib.util.find_spec(m) is None]
    if missing:
        sys.exit(f"This Python ({sys.executable}) is missing: {', '.join(missing)}.\n"
                 "Run:  pip install -r requirements.txt -r requirements-video.txt   then try again.")
    from playwright.sync_api import sync_playwright

    db = Path(os.getenv("EIA_DB_PATH", ROOT / "data" / "eia.sqlite"))
    run_id = a.run_id or latest_run(db, a.company)
    if not run_id:
        print(f"No finished research run for {a.company} yet: running the agent first (a few minutes)...")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "research.py"), a.company], cwd=ROOT, check=False)
        run_id = latest_run(db, a.company)
        if not run_id:
            rows = sqlite3.connect(db).execute("SELECT id, company_json, status FROM runs").fetchall() if db.exists() else []
            sys.exit(f"No finished run with findings for {a.company}. Runs found: " +
                     (", ".join(f"{json.loads(cj).get('name')} [{st}] id={rid}" for rid, cj, st in rows) or "none") +
                     "\nPass one with  --run-id <id>")
    print(f"Using research run {run_id}")

    work = ROOT / "video_build"
    shutil.rmtree(work, ignore_errors=True)
    (work / "frames").mkdir(parents=True)
    scenes = film(a.company)
    chapters = [s for s in scenes if s.chapter]

    if a.tts:
        print("1/4  Synthetic voiceover")
        clips, vlen = voiceover(scenes, work, a.voice)
    else:
        print("1/4  Pacing each scene for a calm read of its voiceover line")
        clips, vlen = [], [len(s.text.split()) / WORDS_PER_SEC + 0.8 for s in scenes]

    print("2/4  Recording the app")
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    app = start_app(port)
    spans = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not a.show)
            ctx = browser.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=W / VW)
            page = ctx.new_page()
            page.goto(f"{base}/?page=overview&run={run_id}")
            page.wait_for_selector(".st-key-nav_overview", timeout=90000)
            page.wait_for_timeout(5000)
            d = Director(page, base, run_id)
            d.ensure_fx()
            page.evaluate("(h) => fx.card(h)", title_card(a.company))
            page.wait_for_timeout(600)
            rec = Recorder(page, work / "frames")
            for i, s in enumerate(scenes):
                # ---- set-up (cut from the video) ----
                if s.key == "dashboard":  # back to the finished run; the new search keeps running in the background
                    page.goto(f"{base}/?page=overview&run={run_id}")
                    page.wait_for_selector(".st-key-nav_overview", timeout=90000)
                    page.wait_for_timeout(5500)
                    d.ensure_fx()
                    page.evaluate("() => fx.veil(true)")
                elif s.page:
                    d.nav(s.page, fade=True)
                d.ensure_fx()
                n = chapters.index(s) + 1 if s.chapter else 0
                page.evaluate("([i, n]) => fx.bar(i, n)", [max(0, n - 1), len(chapters)])
                # ---- the scene ----
                t0 = time.time()
                if s.key == "search":
                    page.evaluate("() => fx.card(null)")
                    d.wait(0.9)
                if s.page or s.key == "dashboard":
                    page.evaluate("() => fx.veil(false)")  # dip from black into the new page
                if s.chapter:
                    page.evaluate("([n, t, c, s]) => fx.chapter(n, t, c, s)", [n, len(chapters), s.chapter, s.sub])
                for stp in s.steps:
                    try:
                        d.step(stp, a.company)
                    except Exception as e:
                        print(f"   ({s.key}: step '{stp[0]}' skipped: {type(e).__name__})")
                        try:
                            page.evaluate("() => { fx.spot(null); fx.zoom(null, 1); }")
                        except Exception:
                            pass
                left = vlen[i] + GAP - (time.time() - t0)
                if left > 0:
                    d.wait(left)
                spans.append((t0, time.time()))
                print(f"   {s.key:15s} {spans[-1][1] - t0:5.1f}s")
            d.wait(0.3)
            rec.stop()
            frames = rec.frames
            browser.close()
    finally:
        app.terminate()

    lengths = [t1 - t0 for t0, t1 in spans]
    print(f"3/4  Assembling {len(frames)} frames")
    video, audio = work / "video.mp4", work / "voice.wav"
    build_video(frames, spans, video, work)
    if a.tts:
        build_audio(clips, lengths, audio, work, Path(a.music) if a.music else None)
    else:  # silent track (some upload sites expect audio), or quiet music if given
        total = sum(lengths)
        if a.music:
            run_ff(["-stream_loop", "-1", "-i", a.music, "-af", f"volume=0.25,atrim=0:{total:.2f},afade=t=in:d=1.5,"
                    f"afade=t=out:st={max(0, total - 2.5):.2f}:d=2.5", "-ar", "48000", "-ac", "2", str(audio)])
        else:
            run_ff(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{total:.2f}", str(audio)])

    print("4/4  Writing the video and your voiceover script")
    out = Path(a.out)
    run_ff(["-i", str(video), "-i", str(audio), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
            "-movflags", "+faststart", str(out)])
    write_srt(scenes, lengths, out.with_suffix(".srt"))
    script = voiceover_script(scenes, lengths, a.company)
    sp = out.with_name("demo_voiceover_script.txt")
    sp.write_text(script, encoding="utf-8")
    dur = media_duration(out)
    print(f"\nDone: {out}  ({dur:.0f}s)\nVoiceover script with timings: {sp}\nGuide subtitles: {out.with_suffix('.srt')}")
    print("\n" + script)
    if dur > 120:
        print("Longer than 2 minutes: some pages took long to load. Run it again, or trim with any video editor.")


ON_SCREEN = {
    "intro": "Animated title card",
    "search": "Company typed into the search bar; live research starts and the progress panel streams",
    "dashboard": "Overview dashboard: price strip, NIFTY 50 benchmark (5Y), financials, ratios, verdict",
    "tabs": "Research summary, Key metrics, Latest developments, Insights tabs",
    "feed": "Discovery Feed; an Evidence Passport opens (quote zoom, Calculations, Challenge and limits)",
    "source": "View page in document: the filing opens with the passage highlighted",
    "modules": "The six module pages, one after another",
    "contradictions": "Contradiction Lab",
    "graph": "Discovery Graph (zoom)",
    "timeline": "Promise-to-cash timeline",
    "report": "Report Studio, then the closing card",
}


def voiceover_script(scenes, lengths, company: str) -> str:
    def mmss(x):
        return f"{int(x) // 60}:{int(x) % 60:02d}"
    t, rows = 0.0, [f"VOICEOVER SCRIPT — Energy Intelligence Agent MVP demo ({company})",
                    f"Total length {mmss(sum(lengths))}. Speak calmly (about 140 words a minute). Start each line at "
                    "its time; it is fine to finish a little early.", ""]
    for i, (s, L) in enumerate(zip(scenes, lengths), 1):
        rows += [f"[{mmss(t)} – {mmss(t + L)}]  {i}. {s.chapter or 'Title'}   (on screen: {ON_SCREEN.get(s.key, '')})",
                 f'    "{s.text}"', ""]
        t += L
    return "\n".join(rows)


if __name__ == "__main__":
    main()
