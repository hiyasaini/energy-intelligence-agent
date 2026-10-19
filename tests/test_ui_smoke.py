"""Drive every dashboard page through a strict Streamlit stand-in.

The stand-in mimics the behaviour the app relies on: widget keys in session_state, button on_click callbacks
running before the next rerun, st.rerun, column configs, and the keyword arguments of current Streamlit
(>=1.46). Unknown st.* attributes raise. It cannot check pixels, so it checks structure and links instead.
"""
import re
import runpy
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["Overview", "Signal Radar", "Discovery Feed", "Promise vs Reality", "Green Growth", "Capital & Cash",
         "Hidden Risk", "Hidden Connections", "Early Warning", "Discovery Graph", "Contradiction Lab", "Timeline",
         "Evidence Explorer", "Report Studio"]
SLUGS = {p.lower().replace(" & ", "-").replace(" ", "-") for p in PAGES}


class Rerun(Exception):
    pass


class Ctx:
    def __init__(self, st):
        self._st = st

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return getattr(self._st, name)


class QueryParams(dict):
    def get(self, k, default=None):
        return super().get(k, default)

    def from_dict(self, d):
        self.clear()
        self.update({k: str(v) for k, v in d.items()})


class FakeSt:
    shared_cache: dict = {}

    def __init__(self, session=None, press=(), query=None):
        self.session_state = session if session is not None else {}
        self.press = set(press)
        self.calls: list[str] = []
        self.callbacks: dict = {}
        self.html: list[str] = []
        self.buttons: list[dict] = []
        self.status_updates: list[tuple] = []
        self._keys: set[str] = set()
        self._cache = FakeSt.shared_cache  # st.cache_resource survives reruns, as in Streamlit
        self.sidebar = Ctx(self)
        self.query_params = QueryParams(query or {})
        self.column_config = types.SimpleNamespace(
            LinkColumn=lambda *a, **k: ("link", a, k), NumberColumn=lambda *a, **k: ("num", a, k),
            TextColumn=lambda *a, **k: ("text", a, k))

    # -- helpers -------------------------------------------------------------------------
    def _key(self, key):
        if key is None:
            return
        assert key not in self._keys, f"duplicate widget key {key}"
        self._keys.add(key)

    def _widget(self, key, default):
        self._key(key)
        if key is None:
            return default
        if key not in self.session_state:
            self.session_state[key] = default
        return self.session_state[key]

    def cache_resource(self, fn):
        def w(*a, **k):
            if fn.__name__ not in self._cache:
                self._cache[fn.__name__] = fn(*a, **k)
            return self._cache[fn.__name__]
        return w

    def fragment(self, func=None, *, run_every=None):
        if func is None:
            return lambda f: f
        return func

    def success(self, t): self.calls.append("success")

    def cache_data(self, ttl=None, show_spinner=True):
        def deco(fn):
            return fn
        return deco

    def rerun(self):
        raise Rerun()

    # -- output ----------------------------------------------------------------------------
    def set_page_config(self, **k): self.calls.append("set_page_config")

    def markdown(self, body, unsafe_allow_html=False):
        assert isinstance(body, str)
        if unsafe_allow_html:
            assert not re.search(r"^\s{4,}<", body, re.M), "indented HTML would render as a code block"
        self.html.append(body)
        self.calls.append("markdown")

    def caption(self, t): assert isinstance(t, str); self.calls.append("caption")
    def info(self, t): self.calls.append("info")
    def warning(self, t): self.calls.append("warning")
    def divider(self): self.calls.append("divider")
    def write(self, *a): self.calls.append("write")

    def plotly_chart(self, fig, config=None, key=None, theme="streamlit", **k):
        import plotly.graph_objects as go
        assert isinstance(fig, go.Figure) and not k, k
        assert theme is None, "Streamlit's chart theme would override the app's colours"
        self._key(key)
        fig.to_json()
        self.calls.append("plotly_chart")

    def dataframe(self, df, hide_index=False, column_config=None, width=None, **k):
        import pandas as pd
        assert isinstance(df, pd.DataFrame) and not k, k
        assert width in (None, "stretch", "content") or isinstance(width, int)
        for c in (column_config or {}):
            assert c in df.columns, f"column_config for missing column {c}"
        for c, cfg in (column_config or {}).items():
            if isinstance(cfg, tuple) and cfg[0] == "link":
                for u in df[c].dropna():
                    assert str(u).startswith(("http://", "https://")), f"unopenable link {u}"
        self.calls.append("dataframe")

    def download_button(self, label, data, file_name, mime, type=None, key=None):
        self._key(key)
        assert isinstance(data, (str, bytes)) and file_name
        self.calls.append("download_button")

    def progress(self, v):
        assert 0 <= v <= 1
        return types.SimpleNamespace(progress=lambda x: None)

    # -- inputs ----------------------------------------------------------------------------
    def radio(self, label, options, key=None, label_visibility="visible", horizontal=False, help=None):
        v = self._widget(key, options[0])
        assert v in options
        return v

    def slider(self, label, lo, hi, value=None, key=None, help=None): return self._widget(key, value)
    def text_input(self, label, placeholder="", key=None, label_visibility="visible", on_change=None, help=None):
        self.callbacks[key] = on_change
        return self._widget(key, "")

    def segmented_control(self, label, options, key=None, label_visibility="visible", on_change=None, default=None):
        self.callbacks[key] = on_change
        v = self._widget(key, default)
        assert v is None or v in options, f"{label}: {v!r}"
        return v

    def popover(self, label, **k):
        assert not k, k
        return Ctx(self)
    def text_area(self, label, key=None, placeholder=""): return self._widget(key, "")

    def selectbox(self, label, options, index=0, format_func=None, key=None, label_visibility="visible"):
        options = list(options)
        if format_func:
            [format_func(o) for o in options]
        v = self._widget(key, options[index] if options else None)
        assert v in options, f"{label}: {v!r} not in options"
        return v

    def multiselect(self, label, options, default=None, format_func=None, key=None):
        if format_func:
            [format_func(o) for o in options]
        return self._widget(key, list(default or []))

    def checkbox(self, label, value=False, key=None): return self._widget(key, value)
    def toggle(self, label, value=False, key=None): return self._widget(key, value)
    def file_uploader(self, *a, key=None, **k): return self._widget(key, [])

    def button(self, label, type=None, on_click=None, args=(), kwargs=None, key=None, disabled=False, help=None):
        self._key(key)
        self.buttons.append({"label": label, "key": key, "on_click": on_click, "args": args, "kwargs": kwargs or {}})
        return (key in self.press or label in self.press) and not disabled

    # -- layout ----------------------------------------------------------------------------
    def columns(self, spec, vertical_alignment="top", gap=None):
        return [Ctx(self) for _ in range(spec if isinstance(spec, int) else len(spec))]

    def container(self, border=None, key=None, height="unset"):
        assert height == "unset" or (isinstance(height, int) and height > 0) or height in ("stretch", "content"), \
            f"invalid container height {height!r}"
        self._key(key)
        return Ctx(self)

    def tabs(self, names): return [Ctx(self) for _ in names]
    def expander(self, label, expanded=False): return Ctx(self)

    def status(self, label, expanded=False):
        outer = self

        class Status(Ctx):
            def update(self, label="", state=""):
                outer.status_updates.append((label, state))
        return Status(self)


def run_app(monkeypatch, session, press=(), query=None):
    fake = FakeSt(session, press, query)
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    try:
        runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
    except Rerun:
        fake.calls.append("rerun")
    session["_last_query"] = dict(fake.query_params)
    return fake


def click(fake, key):
    """Simulate Streamlit's click: run the button's callback, then the next run happens."""
    b = next(b for b in fake.buttons if b["key"] == key)
    if b["on_click"]:
        b["on_click"](*b["args"], **b["kwargs"])


def all_hrefs(fake):
    import html as _h
    return [_h.unescape(u) for u in re.findall(r"href='([^']*)'", " ".join(fake.html))]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("EIA_DB_PATH", str(tmp_path / "ui.sqlite"))
    monkeypatch.setenv("EIA_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("EIA_SEARCH_PROVIDER", "none")
    monkeypatch.setenv("EIA_MARKET_DATA", "none")
    monkeypatch.setenv("EIA_SYNC_JOBS", "1")  # background research runs inline in tests
    FakeSt.shared_cache.clear()  # a fresh "server process" per test


def test_every_page_without_a_run(env, monkeypatch):
    for page in PAGES:
        session = {"nav": page}
        fake = run_app(monkeypatch, session)
        assert fake.calls.count("set_page_config") == 1
        if page not in ("Overview", "Signal Radar"):
            assert any(b["key"] == "need_run_go" for b in fake.buttons), page
            click(fake, "need_run_go")
            assert session["nav"] == "Signal Radar"


def _demo(monkeypatch):
    """Click 'Demo mode' in the top bar: the demo runs inside the callback and the app opens the Overview."""
    session = {"nav": "Overview"}
    fake = run_app(monkeypatch, session)
    click(fake, "mode_demo")
    assert session["nav"] == "Overview" and session["pending_run"] == session["run_id"] and session["mode"] == "Demo mode"
    fake = run_app(monkeypatch, session)
    return session, fake


def test_mode_buttons_switch_both_ways(env, monkeypatch):
    session, fake = _demo(monkeypatch)
    assert any(".st-key-mode_demo button" in h for h in fake.html)  # demo button highlighted
    click(fake, "mode_live")
    assert session["mode"] == "Live research" and session["nav"] == "Signal Radar"
    f = run_app(monkeypatch, session)
    assert any(".st-key-mode_live button" in h for h in f.html) and any(b["key"] == "run_live" for b in f.buttons)
    click(f, "mode_demo")
    assert session["mode"] == "Demo mode" and session["nav"] == "Overview"


def test_demo_lands_on_overview_with_every_panel(env, monkeypatch):
    session, fake = _demo(monkeypatch)
    assert session["nav"] == "Overview" and session["run_select"] == session["run_id"]
    body = " ".join(fake.html)
    for piece in ("Financial performance overview", "Operational metrics", "NIFTY 50 benchmarking", "Balance-sheet ratios",
                  "Agent verdict", "Project pipeline and ESG", "Recent headlines", "Market price", "52-week range",
                  "eia-co", "eia-hero", "Research progress", "Sources analysed", "Key highlights",
                  "Evidence confidence", "Overall outlook", "Financial and operational trends", "Energy mix",
                  "Emissions and sustainability", "Top findings", "Discovery graph", "Recent timeline"):
        assert piece in body, piece
    assert fake.calls.count("plotly_chart") >= 7  # financial, map, gauge, trends, mix, esg, graph
    nav = [b for b in fake.buttons if (b["key"] or "").startswith("nav_")]
    assert len(nav) == 14
    menu = [b for b in fake.buttons if (b["key"] or "").startswith("menu_")]
    assert len(menu) == 14  # top-bar Pages menu mirrors the sidebar
    click(fake, "menu_timeline")
    assert session["nav"] == "Timeline"
    click(fake, "nav_capital-cash")
    assert session["nav"] == "Capital & Cash"
    assert session["_last_query"] == {"page": "overview", "run": session["run_id"]}
    for b in ("hero_feed", "hero_dl"):
        assert any(x["key"] == b for x in fake.buttons) or "download_button" in fake.calls


def test_every_page_with_demo_run_and_links(env, monkeypatch):
    session, _ = _demo(monkeypatch)
    session["mode"] = "Live research"
    for page in PAGES:
        session["nav"] = page
        f = run_app(monkeypatch, session)
        if page not in ("Overview", "Signal Radar"):
            assert any("eia-banner demo" in h for h in f.html), page
        for u in all_hrefs(f):
            if u.startswith("?"):
                q = dict(x.split("=", 1) for x in u[1:].split("&"))
                assert q["page"] in SLUGS and q.get("run") == session["run_id"], u
            else:
                assert u.startswith(("http://", "https://")), f"{page}: link to {u} cannot open in a browser"
        if page in ("Green Growth", "Capital & Cash", "Discovery Graph", "Timeline"):
            assert "plotly_chart" in f.calls, page
        if page == "Report Studio":
            assert f.calls.count("download_button") == 3


def test_html_links_deep_link_into_pages(env, monkeypatch):
    session, fake = _demo(monkeypatch)
    rid = session["run_id"]
    hrefs = [u for u in all_hrefs(fake) if u.startswith("?")]
    risk = next(u for u in hrefs if "filter=risk" in u)
    focus = next(u for u in hrefs if "focus=" in u)
    for href in (risk, focus, f"?page=contradiction-lab&run={rid}", f"?page=evidence-explorer&run={rid}&tab=sources"):
        q = dict(x.split("=", 1) for x in href[1:].split("&"))
        fresh = {}  # a clicked link reloads the page: new session, state comes from the URL
        f = run_app(monkeypatch, fresh, query=q)
        assert fresh["run_id"] == rid and fresh["nav"] == {"discovery-feed": "Discovery Feed",
                                                            "contradiction-lab": "Contradiction Lab",
                                                            "evidence-explorer": "Evidence Explorer"}[q["page"]]
        if "filter" in q:
            assert fresh["feed_dir"] == ["risk"]
        if "focus" in q:
            assert fresh["feed_focus"] == q["focus"]
        # later reruns keep the user's own filter changes
        if q["page"] == "discovery-feed":
            fresh["feed_dir"] = ["opportunity"]
            run_app(monkeypatch, fresh, query=fresh["_last_query"])
            assert fresh["feed_dir"] == ["opportunity"]


def test_top_search_starts_research_immediately(env, monkeypatch):
    session = {"nav": "Overview", "top_search": "NHPC"}
    fake = run_app(monkeypatch, session)
    click(fake, "top_go")
    assert session["nav"] == "Signal Radar" and session["company_query"] == "NHPC" and session["autostart"]
    run_app(monkeypatch, session)  # research starts without pressing anything else (background job)
    assert session.get("job_id")
    f = run_app(monkeypatch, session)  # the progress panel refreshes, sees the finished job, opens results
    assert "rerun" in f.calls and session["pending_nav"] == "Overview"
    f = run_app(monkeypatch, session)
    assert session["nav"] == "Overview" and any(c == "success" for c in f.calls)
    run = __import__("eia.db", fromlist=["Store"]).Store(__import__("os").environ["EIA_DB_PATH"]).get_run(session["run_id"])
    assert run.company.nse == "NHPC" and run.status in ("completed", "partial")
    # nothing reachable in the test, so the Overview explains why and offers next steps
    assert any("found too little to analyse" in h for h in f.html)
    click(f, "empty_retry")
    assert session["nav"] == "Signal Radar" and session["retry_company"]["nse"] == "NHPC"
    run_app(monkeypatch, session)  # retry starts a new background job
    assert "retry_company" not in session
    run_app(monkeypatch, session)  # progress panel sees it finish and opens the new results
    assert session["pending_nav"] == "Overview"


def test_interrupted_run_is_detected(env, monkeypatch):
    from eia.db import Store
    from eia.schema import Company, Run
    import os
    st = Store(os.environ["EIA_DB_PATH"])
    run = Run(company=Company(name="NHPC Ltd", nse="NHPC"), status="running")
    st.save_run(run)
    session = {"nav": "Overview", "run_id": run.id, "run_select": run.id}
    f = run_app(monkeypatch, session)
    assert any("interrupted before it finished" in h for h in f.html)
    session["nav"] = "Discovery Feed"
    f = run_app(monkeypatch, session)
    assert any(b["key"] == "feed_empty_retry" for b in f.buttons)


def test_ambiguous_search_waits_for_a_choice(env, monkeypatch):
    session = {"nav": "Overview", "top_search": "Adani"}
    fake = run_app(monkeypatch, session)
    click(fake, "top_go")
    f = run_app(monkeypatch, session)
    assert "rerun" not in f.calls and session["nav"] == "Signal Radar"


def test_view_page_button_opens_document_with_highlight(env, monkeypatch):
    session, _ = _demo(monkeypatch)
    session["nav"] = "Discovery Feed"
    fake = run_app(monkeypatch, session)
    view = [b for b in fake.buttons if (b["key"] or "").startswith("view_feed_")]
    assert view, "each piece of evidence needs a View page button"
    click(fake, view[0]["key"])
    assert session["nav"] == "Evidence Explorer" and session["doc_source"]
    f = run_app(monkeypatch, session)
    assert session["doc_select"] == session["doc_source"]
    docs = [h for h in f.html if h.startswith("<div class='eia-doc'>")]
    assert docs and "<mark>" in docs[0], "cited passage should be highlighted in the document viewer"


def test_switching_runs_resets_document_state(env, monkeypatch):
    session, fake = _demo(monkeypatch)
    first = session["run_id"]
    click(fake, "mode_demo")  # run the demo a second time
    run_app(monkeypatch, session)
    assert session["run_id"] != first
    session.update(nav="Evidence Explorer", doc_source="stale", run_select=first)
    run_app(monkeypatch, session)
    assert session["run_id"] == first and "doc_source" not in session
