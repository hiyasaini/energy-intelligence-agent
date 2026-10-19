"""Record the hackathon MVP demo video (1-2 min) of the REAL app running on your machine, with a voiceover.

What it does, end to end:
  1. Makes sure a finished research run exists for the company (default NTPC, a NIFTY 50 Track B company);
     if there is none it runs the agent first with scripts/research.py (takes a few minutes).
  2. Starts the Streamlit app, opens it in a headless Chromium and walks through every page while
     capturing the screen at full quality.
  3. Speaks each part of the script (Microsoft neural voice via edge-tts; falls back to the Windows voice).
  4. Keeps only the narrated parts (page loads are cut out), lines video up with the voice, and writes
     demo_video.mp4 plus demo_video.srt subtitles and the narration text.

Usage (from the project folder, inside the virtual environment):
  pip install -r requirements-video.txt
  python -m playwright install chromium
  python scripts/make_demo_video.py                      # NTPC
  python scripts/make_demo_video.py --company "Power Grid" --voice en-IN-PrabhatNeural
"""
from __future__ import annotations

import argparse
import asyncio
import base64
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
VW, VH = 1536, 864         # browser viewport, drawn at 125% so text is readable in the video


# ------------------------------------------------------------------------------------------------
# Script: what is said, and what is shown while it is said
# ------------------------------------------------------------------------------------------------

@dataclass
class Scene:
    key: str
    text: str
    page: str | None = None          # sidebar page slug to open before the scene starts
    actions: list = field(default_factory=list)


def scenes(company: str) -> list[Scene]:
    return [
        Scene("intro",
              "This is the Energy Intelligence Agent, our Track B entry for ATMOS 2026. It is not a chatbot or a "
              "summariser. Given any listed Indian energy company, it researches public evidence on its own, "
              "forms hypotheses, and then tries to disprove them.",
              None, [("title", 0)]),
        Scene("search",
              f"We type a NIFTY 50 company, {company}. The agent resolves its identity, then reads NSE annual "
              "reports, exchange filings, financial tables and market data in the background, with no "
              "company-specific code.",
              None, [("search", company)]),
        Scene("overview",
              "Here is a completed run. The dashboard shows revenue, EBITDA and profit from the filings, capacity, "
              "balance-sheet ratios, NIFTY 50 benchmarking and the agent's verdict. Every number is extracted from "
              "a cited document or calculated in code, never invented by a language model.",
              "overview", [("wait", 3.5), ("scroll", 520), ("wait", 3.5), ("scroll", 520)]),
        Scene("feed",
              "The Discovery Feed ranks findings by severity and evidence strength. Each opens an Evidence "
              "Passport: the discovery, supporting facts with the exact passage and page, the calculations, "
              "the strongest counterargument, a falsification condition, and the evidence strength with its "
              "reasons.",
              "discovery-feed", [("wait", 2.5), ("expand", "Open Evidence Passport"), ("wait", 2.0),
                                 ("scroll", 420), ("wait", 3.0), ("scroll", 420)]),
        Scene("modules",
              "Six modules run on every company: Promise versus Reality, Green Growth, Capital and Cash, "
              "Hidden Risk, Hidden Connections and Early Warning.",
              "promise-vs-reality", [("wait", 1.6), ("nav", "green-growth"), ("wait", 1.6),
                                     ("nav", "capital-cash"), ("wait", 1.6), ("nav", "hidden-risk"), ("wait", 1.4),
                                     ("nav", "early-warning")]),
        Scene("contradictions",
              "The agent runs up to three rounds and actively searches for counter-evidence. Where sources "
              "disagree, the finding stays unresolved instead of being overstated.",
              "contradiction-lab", [("wait", 3.0), ("scroll", 400)]),
        Scene("graph",
              "The Discovery Graph traces each finding back through calculations and facts to its source "
              "documents.",
              "discovery-graph", [("wait", 2.0), ("scroll", 260)]),
        Scene("timeline",
              "The timeline shows when targets were announced, and what was later delivered in operations and "
              "cash.",
              "timeline", [("wait", 2.0), ("scroll", 300)]),
        Scene("evidence",
              "In the Evidence Explorer, every fact opens the original document at the cited page, with the "
              "passage highlighted.",
              "evidence-explorer", [("wait", 2.5), ("scroll", 400)]),
        Scene("report",
              "Finally, Report Studio exports the full research report with clickable source links. The same "
              "system works for any listed energy company, with no manual help.",
              "report-studio", [("wait", 3.0), ("outro", 0)]),
    ]


# ------------------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------------------

def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("ffmpeg not found: run  pip install imageio-ffmpeg")


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
    """Neural voice via edge-tts (needs internet); falls back to the offline Windows/macOS voice (pyttsx3)."""
    try:
        import edge_tts

        async def go():
            await edge_tts.Communicate(text, voice, rate=rate).save(str(out.with_suffix(".mp3")))
        asyncio.run(go())
        return out.with_suffix(".mp3")
    except Exception as e:  # no package, no internet, voice not found
        print(f"   edge-tts unavailable ({type(e).__name__}); using the offline system voice")
        import pyttsx3
        eng = pyttsx3.init()
        eng.setProperty("rate", 172)
        eng.save_to_file(text, str(out.with_suffix(".wav")))
        eng.runAndWait()
        return out.with_suffix(".wav")


def latest_run(db: Path, company: str) -> str | None:
    if not db.exists():
        return None
    con = sqlite3.connect(db)
    q = company.strip().lower()
    rows = con.execute("SELECT id, company_json, status FROM runs WHERE mode != 'demo' AND status IN "
                       "('completed', 'partial') ORDER BY started_at DESC").fetchall()
    for rid, cj, _ in rows:
        c = json.loads(cj)
        names = {str(c.get("name", "")).lower(), str(c.get("nse", "")).lower()}
        if q in names or any(q in n for n in names if n):
            n = con.execute("SELECT COUNT(*) FROM hypotheses WHERE run_id=?", (rid,)).fetchone()[0]
            if n:
                return rid
    return None


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_app(port: int) -> subprocess.Popen:
    env = {**os.environ, "PYTHONUTF8": "1"}
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"), "--server.headless",
                             "true", "--server.port", str(port), "--browser.gatherUsageStats", "false"],
                            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(90):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=2)
            return proc
        except Exception:
            time.sleep(1)
    proc.terminate()
    sys.exit("The Streamlit app did not start. Try  python -m streamlit run app.py  to see the error.")


# ------------------------------------------------------------------------------------------------
# Screen capture: Chrome DevTools screencast (sharp JPEG frames with timestamps)
# ------------------------------------------------------------------------------------------------

class Recorder:
    def __init__(self, page, frames_dir: Path):
        self.dir = frames_dir
        self.frames: list[tuple[float, Path]] = []
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._on_frame)
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 90, "maxWidth": W, "maxHeight": H,
                                               "everyNthFrame": 1})

    def _on_frame(self, ev):
        p = self.dir / f"f{len(self.frames):06d}.jpg"
        p.write_bytes(base64.b64decode(ev["data"]))
        ts = ev.get("metadata", {}).get("timestamp") or time.time()
        self.frames.append((float(ts), p))
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
        except Exception:
            pass

    def stop(self):
        try:
            self.cdp.send("Page.stopScreencast")
        except Exception:
            pass


def build_video(frames: list[tuple[float, Path]], spans: list[tuple[float, float]], out: Path, work: Path) -> None:
    """Concatenate the captured frames inside each narrated span (everything else, e.g. page loads, is cut)."""
    lines = []
    last = None
    for t0, t1 in spans:
        inside = [(t, p) for t, p in frames if t0 < t < t1]
        before = [(t, p) for t, p in frames if t <= t0]
        first = before[-1][1] if before else (inside[0][1] if inside else last)
        if first is None:
            continue
        seq = [(t0, first)] + inside
        for i, (t, p) in enumerate(seq):
            nxt = seq[i + 1][0] if i + 1 < len(seq) else t1
            d = max(0.001, nxt - t)
            lines.append(f"file '{p.resolve().as_posix()}'\nduration {d:.4f}")
            last = p
    lines.append(f"file '{last.resolve().as_posix()}'")  # concat demuxer needs the last file repeated
    lst = work / "frames.txt"
    lst.write_text("\n".join(lines), encoding="utf-8")
    run_ff(["-f", "concat", "-safe", "0", "-i", str(lst), "-vf", f"fps=30,scale={W}:{H}:flags=lanczos,format=yuv420p",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", str(out)])


def build_audio(clips: list[Path], lengths: list[float], out: Path, work: Path) -> None:
    padded = []
    for i, (c, L) in enumerate(zip(clips, lengths)):
        p = work / f"pad{i:02d}.wav"
        run_ff(["-i", str(c), "-af", f"apad=whole_dur={L:.3f},atrim=0:{L:.3f}", "-ar", "48000", "-ac", "2", str(p)])
        padded.append(p)
    lst = work / "audio.txt"
    lst.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in padded), encoding="utf-8")
    run_ff(["-f", "concat", "-safe", "0", "-i", str(lst), "-c:a", "pcm_s16le", str(out)])


def srt(scs: list[Scene], lengths: list[float], out: Path) -> None:
    def ts(x):
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    t, rows = 0.0, []
    for i, (s, L) in enumerate(zip(scs, lengths), 1):
        rows.append(f"{i}\n{ts(t + 0.2)} --> {ts(t + L - 0.3)}\n{s.text}\n")
        t += L
    out.write_text("\n".join(rows), encoding="utf-8")


# ------------------------------------------------------------------------------------------------
# Browser actions
# ------------------------------------------------------------------------------------------------

OVERLAY = """(html) => { let d = document.getElementById('demo-ov'); if (!d) { d = document.createElement('div');
 d.id = 'demo-ov'; document.body.appendChild(d); }
 d.style.cssText = 'position:fixed;inset:0;z-index:99999;display:flex;flex-direction:column;align-items:center;' +
 'justify-content:center;background:radial-gradient(circle at 50% 40%,#10233F 0%,#070D1A 70%);color:#E6EDF7;' +
 'font-family:Inter,Segoe UI,sans-serif;text-align:center;transition:opacity .6s;opacity:1';
 d.innerHTML = html; }"""


def title_html(company: str) -> str:
    return ("<div style='font-size:22px;letter-spacing:.3em;color:#22C7E8;font-weight:700'>ATMOS 2026 · TRACK B</div>"
            "<div style='font-size:76px;font-weight:800;margin:18px 0 10px'>Energy Intelligence Agent</div>"
            "<div style='font-size:28px;color:#93A4BE'>Autonomous financial research for listed Indian energy companies"
            "</div><div style='margin-top:46px;font-size:22px;color:#C9D5E6'>Discover · Connect · Calculate · Reason · "
            "Challenge · Prove</div>"
            f"<div style='margin-top:18px;font-size:18px;color:#62748F'>MVP demo, live run on {company}</div>")


def outro_html() -> str:
    return ("<div style='font-size:64px;font-weight:800'>Energy Intelligence Agent</div>"
            "<div style='font-size:26px;color:#93A4BE;margin-top:14px'>Evidence-backed discoveries, "
            "every claim traceable to its source</div>"
            "<div style='margin-top:40px;font-size:20px;color:#22C7E8'>ATMOS 2026 · Finding the Next Signal · Track B"
            "</div>")


def remove_overlay(page):
    page.evaluate("() => { const d = document.getElementById('demo-ov'); if (d) { d.style.opacity = 0;"
                  " setTimeout(() => d.remove(), 650); } }")


def scroll(page, dy: int):
    page.mouse.move(VW * 0.6, VH * 0.6)
    steps = 12
    for _ in range(steps):  # smooth
        page.mouse.wheel(0, dy / steps)
        page.wait_for_timeout(35)


def nav(page, slug: str, base: str, run_id: str):
    btn = page.locator(f".st-key-nav_{slug} button")
    try:
        btn.first.click(timeout=4000)
    except Exception:  # sidebar hidden or a different Streamlit build: fall back to the deep link
        page.goto(f"{base}/?page={slug}&run={run_id}")
    page.wait_for_timeout(2600)
    page.mouse.move(VW * 0.6, VH * 0.3)
    page.evaluate("() => { const m = document.querySelector('section.main, [data-testid=\"stMain\"]');"
                  " if (m) m.scrollTo(0, 0); window.scrollTo(0, 0); }")
    page.wait_for_timeout(400)


def do(page, action, arg, base: str, run_id: str):
    if action == "wait":
        page.wait_for_timeout(int(arg * 1000))
    elif action == "scroll":
        scroll(page, arg)
    elif action == "nav":
        page.locator(f".st-key-nav_{arg} button").first.click(timeout=4000)
        page.wait_for_timeout(300)
    elif action == "expand":
        try:
            page.get_by_text(arg).first.click(timeout=4000)
        except Exception:
            pass
    elif action == "title":
        pass  # overlay already shown before the scene began
    elif action == "outro":
        page.wait_for_timeout(1500)
        page.evaluate(OVERLAY, outro_html())
        page.wait_for_timeout(4000)
    elif action == "search":
        box = page.get_by_placeholder(re.compile("Search company", re.I)).first
        box.click(timeout=6000)
        box.fill("")
        box.type(arg, delay=120)
        page.wait_for_timeout(500)
        box.press("Enter")
        page.wait_for_timeout(9000)  # progress panel streaming "Reading 1/8 ..." messages


# ------------------------------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--company", default="NTPC", help="NIFTY 50 company from Track B (default NTPC)")
    ap.add_argument("--run-id", default=None, help="use this research run instead of the latest one")
    ap.add_argument("--voice", default="en-IN-NeerjaNeural",
                    help="edge-tts voice, e.g. en-IN-PrabhatNeural, en-US-AriaNeural, en-GB-RyanNeural")
    ap.add_argument("--rate", default="+4%", help="speaking rate for edge-tts, e.g. +0%%, +8%%")
    ap.add_argument("--out", default=str(ROOT / "demo_video.mp4"))
    ap.add_argument("--show", action="store_true", help="show the browser window while recording")
    a = ap.parse_args()

    from playwright.sync_api import sync_playwright

    db = Path(os.getenv("EIA_DB_PATH", ROOT / "data" / "eia.sqlite"))
    run_id = a.run_id or latest_run(db, a.company)
    if not run_id:
        print(f"No finished research run for {a.company} yet: running the agent first (a few minutes)...")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "research.py"), a.company], cwd=ROOT, check=False)
        run_id = latest_run(db, a.company)
        if not run_id:
            sys.exit(f"The research run for {a.company} produced no findings, so there is nothing to show.")
    print(f"Using research run {run_id}")

    work = ROOT / "video_build"
    shutil.rmtree(work, ignore_errors=True)
    (work / "frames").mkdir(parents=True)
    scs = scenes(a.company)

    print("1/4  Recording the voiceover")
    clips, voice_len = [], []
    for i, s in enumerate(scs):
        c = speak(s.text, work / f"vo{i:02d}_{s.key}", a.voice, a.rate)
        clips.append(c)
        voice_len.append(media_duration(c))
        print(f"   {s.key:15s} {voice_len[-1]:5.1f}s")
    total = sum(voice_len) + 0.7 * len(scs)
    print(f"   narration {total:.0f}s" + ("  (over 2 minutes: try --rate +10%)" if total > 118 else ""))

    print("2/4  Starting the app and recording the screen")
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    app = start_app(port)
    spans: list[tuple[float, float]] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not a.show)
            ctx = browser.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=W / VW)
            page = ctx.new_page()
            page.goto(f"{base}/?page=overview&run={run_id}")
            page.wait_for_selector(".st-key-nav_overview", timeout=60000)
            page.wait_for_timeout(4000)
            rec = Recorder(page, work / "frames")
            for i, s in enumerate(scs):
                if s.key == "intro":
                    page.evaluate(OVERLAY, title_html(a.company))
                    page.wait_for_timeout(800)
                elif s.key == "search":
                    remove_overlay(page)
                    page.wait_for_timeout(900)
                elif s.page:
                    if s.key == "overview":  # back to the finished run (the new search keeps running in the background)
                        page.goto(f"{base}/?page=overview&run={run_id}")
                        page.wait_for_selector(".st-key-nav_overview", timeout=60000)
                        page.wait_for_timeout(5000)
                    else:
                        nav(page, s.page, base, run_id)
                length = voice_len[i] + 0.7
                t0 = time.time()
                for act, arg in s.actions:
                    try:
                        do(page, act, arg, base, run_id)
                    except Exception as e:
                        print(f"   ({s.key}: '{act}' skipped: {type(e).__name__})")
                left = length - (time.time() - t0)
                if left > 0:
                    page.wait_for_timeout(int(left * 1000))
                t1 = time.time()
                spans.append((t0, t1))
                print(f"   {s.key:15s} recorded {t1 - t0:5.1f}s")
            page.wait_for_timeout(300)
            rec.stop()
            frames = rec.frames
            browser.close()
    finally:
        app.terminate()

    lengths = [t1 - t0 for t0, t1 in spans]
    print(f"3/4  Building the video from {len(frames)} frames")
    video = work / "video.mp4"
    build_video(frames, spans, video, work)
    audio = work / "voice.wav"
    build_audio(clips, lengths, audio, work)

    print("4/4  Adding the voiceover")
    out = Path(a.out)
    run_ff(["-i", str(video), "-i", str(audio), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
            "-movflags", "+faststart", str(out)])
    srt(scs, lengths, out.with_suffix(".srt"))
    out.with_name("demo_narration.txt").write_text("\n\n".join(s.text for s in scs), encoding="utf-8")
    dur = media_duration(out)
    print(f"\nDone: {out}  ({dur:.0f}s)\nSubtitles: {out.with_suffix('.srt')}")
    if dur > 120:
        print("Note: longer than 2 minutes; run again with  --rate +12%  to speed the voice up.")


if __name__ == "__main__":
    main()
