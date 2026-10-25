"""Visual system: deep navy panels, cyan primary, green opportunity, amber caution, coral risk, violet links.
Layout follows the product mockup: icon sidebar, top search bar, company header with KPI tiles, panel grid."""
from __future__ import annotations

import html as _html

BG = "#0B0F19"
PANEL = "#0F172A"          # slate-900
PANEL2 = "#111A2E"
RAISED = "#1E293B"         # slate-800
RULE = "#1E293B"
TEXT = "#E2E8F0"           # slate-200
MUTED = "#94A3B8"          # slate-400
FAINT = "#64748B"          # slate-500
CYAN = "#14B8A6"           # neon teal: primary
TEAL_HI = "#2DD4BF"        # teal-400
BLUE = "#3B82F6"           # electric blue: data streams
GREEN = "#10B981"          # emerald
MINT = "#34D399"           # emerald-400
AMBER = "#F59E0B"
CORAL = "#EF4444"
VIOLET = "#8B5CF6"
ORANGE = "#F97316"

STATUS = {
    "Supported": (TEAL_HI, "#042F2E"),
    "Pending counter-check": (AMBER, "#33240A"),
    "Unresolved": (AMBER, "#33240A"),
    "Weakened": (AMBER, "#2E220B"),
    "Rejected": (CORAL, "#36161A"),
    "Insufficient evidence": (MUTED, "#18233A"),
}
DIRECTION = {"risk": ("Risk", CORAL), "opportunity": ("Opportunity", GREEN), "neutral": ("Observation", MUTED)}
MODULE_STATUS = {"ok": ("Sufficient data", TEAL_HI, "#042F2E"), "partial": ("Partial data", AMBER, "#33240A"),
                 "insufficient_data": ("Insufficient data", MUTED, "#18233A"), "error": ("Module error", CORAL, "#36161A")}
STRENGTH_LEVEL = {"insufficient": 0, "weak": 1, "moderate": 2, "strong": 3}
STRENGTH_CHIP = {"strong": (MINT, "#052E1F"), "moderate": (AMBER, "#33240A"), "weak": (ORANGE, "#33190A"),
                 "insufficient": (MUTED, "#18233A")}
# Chart palette: categorical hues stepped for a dark surface and checked for colour-blind separation.
# Used in fixed order (never cycled); UI chrome keeps the brand cyan above.
C_BLUE, C_ORANGE, C_AQUA, C_YELLOW = "#3B82F6", "#F59E0B", "#14B8A6", "#EAB308"
C_MAGENTA, C_GREEN, C_VIOLET, C_RED = "#EC4899", "#10B981", "#8B5CF6", "#EF4444"
C_GREY = "#7D8BA0"
SERIES_COLORS = [C_BLUE, C_ORANGE, C_AQUA, C_VIOLET, C_MAGENTA, C_GREEN, C_YELLOW, C_RED]
SOURCE_COLORS = {"Coal": C_GREY, "Solar": C_YELLOW, "Wind": C_AQUA, "Hydro": C_BLUE, "Gas": C_ORANGE,
                 "Nuclear": C_VIOLET}

FONT = "'Inter', 'Segoe UI', system-ui, -apple-system, Roboto, sans-serif"
MONO = "'JetBrains Mono', 'Cascadia Mono', Consolas, 'SFMono-Regular', Menlo, monospace"


def esc(s) -> str:
    """Escape for HTML inside st.markdown; '$' escaped so Streamlit never renders maths."""
    return _html.escape("" if s is None else str(s)).replace("$", "&#36;")


# ---- sidebar icons (simple stroke drawings, masked so they take the text colour) -------------------
ICONS = [
    "M3 11l9-7 9 7M5 10v10h5v-6h4v6h5V10",                                                   # overview
    "M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0-18 0M12 12m-4 0a4 4 0 1 0 8 0a4 4 0 1 0-8 0M12 12l6-6",  # radar
    "M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01",                               # feed
    "M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0-18 0M12 12m-5 0a5 5 0 1 0 10 0a5 5 0 1 0-10 0M12 12h.01",  # promise
    "M5 20c0-9 6-15 15-16-1 9-6 15-15 16zM5 20l8-8",                                         # green growth
    "M3 7h18v12H3zM3 7l3-3h12l3 3M16 13h2",                                                  # capital
    "M12 3l10 18H2zM12 10v5M12 18h.01",                                                      # hidden risk
    "M6 12m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M18 6m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M18 18m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M8 11l8-4M8 13l8 4",
    "M3 12h4l3-8 4 16 3-8h4",                                                                # early warning
    "M12 5m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M5 19m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M19 19m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M11 7l-5 10M13 7l5 10M7 19h10",
    "M12 3v18M6 21h12M4 7h16M7 7l-3 7h6zM17 7l-3 7h6z",                                      # contradiction lab
    "M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0-18 0M12 7v5l3 2",                                  # timeline
    "M11 11m-7 0a7 7 0 1 0 14 0a7 7 0 1 0-14 0M21 21l-5-5",                                  # evidence
    "M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h7",                                               # report
]


def _icon_url(path: str) -> str:
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' "
           f"stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='{path}'/></svg>")
    return "data:image/svg+xml;utf8," + svg.replace("#", "%23").replace('"', "'")


# Two selectors per icon so it works whether Streamlit renders the options as sibling <label>s or wraps each
# <label> in its own <div> (differs between versions).
_ICON_CSS = "".join(
    f'section[data-testid="stSidebar"] div[role="radiogroup"] label:nth-of-type({i + 1})::before,'
    f'section[data-testid="stSidebar"] div[role="radiogroup"] > div:nth-child({i + 1}) label::before'
    f'{{-webkit-mask-image:url("{_icon_url(p)}");mask-image:url("{_icon_url(p)}");}}'
    for i, p in enumerate(ICONS))

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, .stApp, [class*="css"], button, input, textarea { font-family: FONT; }
.stApp { color: TEXT; background-color: BG;
  background-image:
    radial-gradient(900px 500px at 8% -10%, rgba(20,184,166,.16), transparent 60%),
    radial-gradient(800px 480px at 100% 0%, rgba(139,92,246,.13), transparent 60%),
    radial-gradient(900px 600px at 50% 120%, rgba(59,130,246,.10), transparent 60%);
  background-attachment: fixed; }
footer, [data-testid="stDecoration"], [data-testid="stStatusWidget"], [data-testid="stAppDeployButton"],
.stDeployButton, #MainMenu { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"],
[data-testid="stSidebarCollapseButton"] { visibility: visible !important; display: flex !important; opacity: 1 !important;
  z-index: 1000; }
[data-testid="stSidebarCollapsedControl"] button, [data-testid="stExpandSidebarButton"] {
  background: rgba(15,23,42,.8) !important; border: 1px solid CYAN !important; border-radius: 10px !important;
  color: #FFFFFF !important; box-shadow: 0 0 18px rgba(20,184,166,.35); }
.block-container, [data-testid="stMainBlockContainer"] { padding-top: 2.4rem !important; padding-bottom: 3rem; max-width: 100% !important;
  padding-left: 2rem !important; padding-right: 2rem !important; }
p, li, span, div { font-variant-numeric: tabular-nums; }
a { color: TEAL_HI !important; text-decoration: none !important; }
a:hover { text-decoration: underline !important; }
:focus-visible { outline: 2px solid CYAN !important; outline-offset: 2px; }
h1, h2, h3, h4 { color: #F8FAFC !important; letter-spacing: -.02em; }
::selection { background: rgba(20,184,166,.35); }
::-webkit-scrollbar { width: 10px; height: 10px; } ::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #1E293B; border-radius: 10px; border: 2px solid BG; }
::-webkit-scrollbar-thumb:hover { background: #334155; }

/* sidebar: command center */
section[data-testid="stSidebar"] { background: rgba(9,13,24,.82); backdrop-filter: blur(14px);
  border-right: 1px solid rgba(30,41,59,.8); }
section[data-testid="stSidebar"][aria-expanded="true"] { min-width: 250px; }
section[data-testid="stSidebar"][aria-expanded="false"] { min-width: 0 !important; width: 0 !important; max-width: 0 !important;
  border-right: none; overflow: hidden; }
section[data-testid="stSidebar"] .block-container, section[data-testid="stSidebar"] [data-testid="stSidebarContent"] { padding-top: .6rem; }
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p { font-size: .68rem !important; letter-spacing: .14em;
  text-transform: uppercase; color: FAINT !important; font-weight: 600; }
section[data-testid="stSidebar"] hr { border-color: rgba(30,41,59,.8); }
ICON_CSS
.eia-navlbl { font-size: .66rem; letter-spacing: .16em; text-transform: uppercase; color: FAINT; font-weight: 700;
  margin: 0; padding: 4px 0 10px 12px; line-height: 1.2; }
.eia-user { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 14px; margin-top: 6px;
  background: rgba(15,23,42,.6); border: 1px solid rgba(30,41,59,.8); }
.eia-user .av { width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; flex: 0 0 36px;
  background: linear-gradient(135deg, CYAN, VIOLET); color: #FFFFFF; font-weight: 700; font-size: .8rem;
  box-shadow: 0 0 0 2px BG, 0 0 0 3px rgba(20,184,166,.6); }
.eia-user .nm { font-weight: 600; font-size: .86rem; color: #F8FAFC; }
.eia-user .rl { font-size: .72rem; color: MUTED; display: flex; align-items: center; gap: 6px; }
.eia-user .rl::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: MINT; box-shadow: 0 0 8px MINT; }

/* brand */
.eia-brand { display: flex; align-items: center; gap: 11px; margin: 2px 0 20px; }
.eia-brand .mark { width: 38px; height: 38px; border-radius: 12px; flex: 0 0 38px; display: grid; place-items: center;
  background: linear-gradient(135deg, CYAN, GREEN 45%, VIOLET); box-shadow: 0 6px 22px -6px rgba(20,184,166,.7); }
.eia-brand .mark span { color: #FFFFFF; font-weight: 800; font-size: 16px; }
.eia-brand .name { font-weight: 700; font-size: .92rem; color: #F8FAFC; line-height: 1.15; white-space: nowrap; letter-spacing: -.01em; }
.eia-brand .ai { display: inline-block; margin-left: 6px; padding: 1px 7px; border-radius: 999px;
  background: rgba(139,92,246,.18); border: 1px solid rgba(139,92,246,.5); color: #C4B5FD; font-size: .62rem; font-weight: 700;
  vertical-align: 2px; }
.eia-brand .tag { color: FAINT; font-size: .66rem; margin-top: 3px; white-space: nowrap; }

/* glass cards */
div[class*="st-key-panel"] { background: rgba(15,23,42,.6); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(30,41,59,.8) !important; border-radius: 16px; padding: 14px 16px 20px !important;
  height: auto; overflow: visible;
  box-shadow: 0 1px 0 rgba(255,255,255,.04) inset, 0 20px 40px -24px rgba(0,0,0,.8); transition: border-color .2s, box-shadow .2s; }
div[class*="st-key-panel"]:hover { border-color: rgba(20,184,166,.35) !important;
  box-shadow: 0 1px 0 rgba(255,255,255,.05) inset, 0 0 0 1px rgba(20,184,166,.12), 0 20px 40px -20px rgba(20,184,166,.25); }
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div[class*="st-key-panel"]) { border: none !important; }
/* active card: gradient border */
div[class*="st-key-panel_kpi_"]:first-of-type, div.st-key-panel_disc_active, div[class*="st-key-panel_chat"] {
  border: 1px solid transparent !important;
  background: linear-gradient(rgba(13,20,36,.92), rgba(13,20,36,.92)) padding-box,
              linear-gradient(135deg, rgba(20,184,166,.7), rgba(59,130,246,.35) 45%, rgba(139,92,246,.6)) border-box; }
.eia-ptitle { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin: 2px 0 12px;
  font-weight: 600; font-size: .98rem; color: #F8FAFC; letter-spacing: -.01em; }
.eia-ptitle .right { font-size: .78rem; font-weight: 500; color: MUTED; }
.eia-ptitle .big { color: TEAL_HI; font-size: 1.1rem; font-weight: 700; }

/* buttons, inputs */
.stButton > button, .stDownloadButton > button, [data-testid="stPopover"] button {
  border-radius: 10px; border: 1px solid rgba(51,65,85,.9); background: rgba(15,23,42,.7); color: TEXT; font-weight: 600;
  min-height: 40px; transition: all .18s ease; }
.stButton > button:hover, .stDownloadButton > button:hover { border-color: CYAN; color: TEAL_HI;
  box-shadow: 0 0 0 3px rgba(20,184,166,.12); transform: translateY(-1px); }
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
  background: linear-gradient(135deg, #14B8A6, #10B981); color: #FFFFFF; border: none;
  box-shadow: 0 8px 22px -8px rgba(16,185,129,.7); }
.stButton > button[kind="primary"]:hover { filter: brightness(1.08); color: #FFFFFF; }
.stTextInput input, .stNumberInput input, div[data-baseweb="select"] > div, .stTextArea textarea {
  background: rgba(15,23,42,.7) !important; border: 1px solid rgba(51,65,85,.9) !important; border-radius: 12px !important;
  color: TEXT !important; min-height: 42px; }
.stTextInput input:focus, .stTextArea textarea:focus { border-color: CYAN !important; box-shadow: 0 0 0 3px rgba(20,184,166,.18) !important; }
.stTextInput input::placeholder { color: FAINT; }
div[data-testid="stExpander"] { background: rgba(15,23,42,.6); border: 1px solid rgba(30,41,59,.8); border-radius: 14px; }
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: none; background: rgba(15,23,42,.6); padding: 4px;
  border-radius: 12px; border: 1px solid rgba(30,41,59,.8); width: fit-content; max-width: 100%; }
.stTabs [data-baseweb="tab"] { padding: 7px 14px; color: MUTED; font-weight: 600; border-radius: 9px; height: auto; }
.stTabs [aria-selected="true"] { color: #FFFFFF !important; background: linear-gradient(135deg, rgba(20,184,166,.25), rgba(59,130,246,.18)); }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none; }
div[data-testid="stDataFrame"] { border: 1px solid rgba(30,41,59,.8); border-radius: 12px; }
[data-testid="stSegmentedControl"] button, div[data-baseweb="button-group"] button { border-radius: 9px !important; }
span[data-baseweb="tag"] { background: rgba(20,184,166,.15) !important; border: 1px solid rgba(20,184,166,.45) !important;
  border-radius: 999px !important; }
span[data-baseweb="tag"] span, span[data-baseweb="tag"] svg { color: TEAL_HI !important; fill: TEAL_HI !important; }
[data-testid="stWidgetLabel"] p { color: MUTED !important; font-size: .84rem !important; }

/* KPI cards (top metrics bar) */
.eia-k { padding: 8px 8px 4px; min-height: 120px; position: relative; }
.eia-k .top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.eia-k .lb { color: MUTED; font-size: .8rem; font-weight: 500; }
.eia-k .ic { width: 32px; height: 32px; border-radius: 10px; display: grid; place-items: center; font-size: .95rem; }
.eia-k .v { font-size: 1.75rem; font-weight: 700; color: #F8FAFC; letter-spacing: -.02em; margin: 6px 0 4px; line-height: 1.1;
  white-space: nowrap; }
.eia-k .v small { font-size: .95rem; font-weight: 600; color: MUTED; margin-left: 4px; }
.eia-k .ft { display: flex; align-items: center; gap: 8px; font-size: .74rem; color: FAINT; flex-wrap: wrap; }
.eia-k .row { display: flex; align-items: center; gap: 14px; }
.eia-pill { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 999px; font-size: .72rem;
  font-weight: 700; }
.eia-pill.up { color: MINT; background: rgba(16,185,129,.14); border: 1px solid rgba(16,185,129,.35); }
.eia-pill.down { color: #FCA5A5; background: rgba(239,68,68,.14); border: 1px solid rgba(239,68,68,.35); }
.eia-pill.flat { color: MUTED; background: rgba(148,163,184,.1); border: 1px solid rgba(148,163,184,.25); }

/* company header */
.eia-co { display: flex; gap: 14px; align-items: center; padding: 4px 6px; height: 100%; }
.eia-co .logo { width: 56px; height: 56px; border-radius: 14px; display: grid; place-items: center; flex: 0 0 56px;
  background: linear-gradient(135deg, rgba(20,184,166,.25), rgba(139,92,246,.25)); border: 1px solid rgba(20,184,166,.45);
  color: #F8FAFC; font-weight: 800; font-size: 1.05rem; }
.eia-co .n { font-size: 1.3rem; font-weight: 700; color: #F8FAFC; line-height: 1.15; overflow: hidden; letter-spacing: -.02em;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.eia-co > div:last-child { min-width: 0; }
.eia-co .ids { color: MUTED; font-size: .84rem; margin: 4px 0 6px; }
.eia-tag { display: inline-block; padding: 2px 10px; margin: 0 6px 4px 0; border: 1px solid rgba(51,65,85,.9); border-radius: 999px;
  background: rgba(15,23,42,.7); color: #CBD5E1; font-size: .74rem; }

.eia-kpi { padding: 12px 16px 10px; min-height: 118px; }
.eia-kpi .v { font-size: 1.3rem; font-weight: 700; color: #F8FAFC; display: flex; justify-content: space-between;
  align-items: baseline; gap: 6px; white-space: nowrap; }
.eia-kpi .ch { font-size: .8rem; font-weight: 600; }
.eia-kpi .l { color: MUTED; font-size: .8rem; margin: 2px 0 6px; }
.eia-kpi .src { color: FAINT; font-size: .7rem; }
.eia-meter { height: 6px; border-radius: 999px; background: rgba(51,65,85,.6); overflow: hidden; margin-top: 10px; }
.eia-meter > div { height: 100%; border-radius: 999px; }

/* hero */
.eia-hero { position: relative; border-radius: 14px; overflow: hidden; padding: 20px 22px 14px; min-height: 196px;
  background: linear-gradient(100deg, rgba(11,15,25,.96) 0%, rgba(11,15,25,.82) 45%, rgba(11,15,25,.3) 100%),
              linear-gradient(160deg, #0F3B3A 0%, #1E1B4B 60%, #312E81 100%); }
.eia-hero svg.sky { position: absolute; right: 0; bottom: 0; height: 100%; opacity: .9; }
.eia-hero .chip { display: inline-flex; gap: 6px; align-items: center; padding: 3px 10px; border-radius: 999px;
  background: rgba(16,185,129,.15); border: 1px solid rgba(16,185,129,.45); color: MINT; font-size: .72rem; font-weight: 700; }
.eia-hero .t { position: relative; font-size: 1.75rem; font-weight: 700; color: #FFFFFF; margin: 12px 0 6px; line-height: 1.2; letter-spacing: -.02em; }
.eia-hero .s { position: relative; color: #CBD5E1; font-size: .95rem; }
.eia-hero .s b { color: TEAL_HI; } .eia-hero .s b.g { color: MINT; }
.eia-hero .u { position: relative; color: MUTED; font-size: .8rem; margin-top: 6px; }

/* progress + sources */
.eia-bar { height: 6px; border-radius: 999px; background: rgba(51,65,85,.6); margin: 0 0 12px; overflow: hidden; }
.eia-bar > div { height: 100%; background: linear-gradient(90deg, CYAN, BLUE, VIOLET); border-radius: 999px;
  box-shadow: 0 0 12px rgba(20,184,166,.6); }
.eia-step { display: flex; align-items: center; gap: 10px; padding: 5px 0; font-size: .88rem; color: #CBD5E1; }
.eia-step .ok { width: 18px; height: 18px; border-radius: 50%; display: grid; place-items: center; flex: 0 0 18px;
  font-size: 11px; font-weight: 800; }
.eia-step .v { margin-left: auto; color: TEXT; font-weight: 600; white-space: nowrap; }
.eia-srow { display: flex; align-items: center; gap: 10px; padding: 5px 0; font-size: .88rem; color: #CBD5E1; }
.eia-srow .ic { width: 8px; height: 8px; border-radius: 50%; background: CYAN; flex: 0 0 8px; box-shadow: 0 0 8px CYAN; }
.eia-srow .v { margin-left: auto; font-weight: 600; color: TEXT; }

/* highlight tiles */
.eia-hl { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.eia-hl a.tile { display: block; border-radius: 14px; padding: 12px 16px; min-height: 84px; border: 1px solid;
  text-decoration: none !important; position: relative; transition: transform .18s; }
.eia-hl a.tile:hover { transform: translateY(-2px); filter: brightness(1.15); }
.eia-hl .n { font-size: 1.9rem; font-weight: 700; line-height: 1.1; }
.eia-hl .l { font-size: .84rem; margin-top: 6px; }
.eia-hl .ic { position: absolute; right: 14px; top: 14px; font-size: 1.1rem; opacity: .9; }
@media (max-width: 1100px) { .eia-hl { grid-template-columns: repeat(2, 1fr); } }

.eia-ring { display: flex; gap: 18px; align-items: center; }
.eia-ring .lg div { display: flex; align-items: center; gap: 8px; color: #CBD5E1; font-size: .86rem; padding: 3px 0; }
.eia-ring .lg i { width: 9px; height: 9px; border-radius: 50%; display: inline-block; box-shadow: 0 0 8px currentColor; }
.eia-outlook { display: flex; gap: 14px; align-items: flex-start; }
.eia-outlook .badge { width: 42px; height: 42px; border-radius: 12px; display: grid; place-items: center; flex: 0 0 42px;
  border: 1px solid; font-size: 1.1rem; }
.eia-outlook .h { font-weight: 700; font-size: 1.02rem; margin-bottom: 4px; }
.eia-outlook .p { color: MUTED; font-size: .86rem; line-height: 1.5; }

.eia-find-li { display: flex; gap: 12px; align-items: flex-start; padding: 9px 0; border-bottom: 1px solid rgba(30,41,59,.8); }
.eia-find-li:last-child { border-bottom: none; }
.eia-find-li .num { width: 26px; height: 26px; border-radius: 8px; display: grid; place-items: center; flex: 0 0 26px;
  font-weight: 700; color: #04101A; font-size: .8rem; }
.eia-find-li .t { font-weight: 600; color: #F8FAFC; font-size: .92rem; }
.eia-find-li .d { color: MUTED; font-size: .8rem; margin-top: 2px; }
.eia-find-li .chip { margin-left: auto; }
.eia-tl { position: relative; }
.eia-tl .row { display: flex; gap: 12px; padding: 6px 0; font-size: .84rem; align-items: flex-start; }
.eia-tl .dt { width: 74px; flex: 0 0 74px; color: TEAL_HI; font-weight: 600; }
.eia-tl .dot { width: 9px; height: 9px; border-radius: 50%; background: CYAN; margin-top: 5px; flex: 0 0 9px;
  box-shadow: 0 0 0 3px rgba(20,184,166,.15), 0 0 10px CYAN; }
.eia-tl .tx { color: #CBD5E1; }
.eia-mix .row { display: flex; gap: 10px; align-items: center; font-size: .86rem; color: #CBD5E1; padding: 4px 0; }
.eia-mix i { width: 9px; height: 9px; border-radius: 50%; box-shadow: 0 0 8px currentColor; }
.eia-mix .v { margin-left: auto; font-weight: 700; color: #F8FAFC; }

/* shared pieces */
.eia-title { font-size: 1.75rem; font-weight: 800; margin: .3rem 0 .25rem; letter-spacing: -.03em;
  background: linear-gradient(90deg, #F8FAFC, #99F6E4 60%, #C4B5FD); -webkit-background-clip: text; background-clip: text; color: transparent; }
.eia-sub { color: MUTED; font-size: .95rem; max-width: 80ch; margin: 0 0 1.1rem; }
.eia-h { font-size: 1.02rem; font-weight: 700; margin: 1.3rem 0 .6rem; color: #F8FAFC; letter-spacing: -.01em; }
.eia-muted { color: MUTED; font-size: .88rem; }
.eia-faint { color: FAINT; font-size: .8rem; }
.eia-empty { color: MUTED; font-size: .88rem; padding: 18px 4px; }
.eia-banner { padding: 10px 14px; border-radius: 12px; margin-bottom: 1rem; font-size: .92rem; }
.eia-banner.demo { background: rgba(245,158,11,.1); border: 1px solid rgba(245,158,11,.45); color: #FDE68A; }
.eia-banner.live { background: rgba(15,23,42,.6); border: 1px solid rgba(30,41,59,.8); color: TEXT; display: flex; gap: 14px; flex-wrap: wrap; }
.eia-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin: .4rem 0 1.1rem; }
.eia-stat { padding: 14px 18px; border-radius: 14px; background: rgba(15,23,42,.6); border: 1px solid rgba(30,41,59,.8);
  backdrop-filter: blur(10px); }
.eia-stat .v { font-size: 1.6rem; font-weight: 700; color: #F8FAFC; letter-spacing: -.02em; }
.eia-stat .l { color: MUTED; font-size: .82rem; margin-top: 4px; }
.eia-stat .n { color: FAINT; font-size: .76rem; }
.eia-stat.accent .v { color: TEAL_HI; text-shadow: 0 0 18px rgba(20,184,166,.45); }
.eia-stat.warn .v { color: AMBER; } .eia-stat.bad .v { color: CORAL; }
.eia-chip { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 999px; font-size: .74rem;
  font-weight: 600; margin: 0 6px 4px 0; border: 1px solid transparent; white-space: nowrap; }
.eia-chip::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; box-shadow: 0 0 8px currentColor; }
.eia-dir { font-size: .78rem; font-weight: 700; margin-right: 10px; }
.eia-gauge { display: inline-flex; align-items: center; gap: 8px; vertical-align: middle; }
.eia-gauge .seg { display: inline-block; width: 18px; height: 6px; border-radius: 999px; background: rgba(51,65,85,.7); margin-right: 3px; }
.eia-gauge .lbl { font-size: .78rem; color: MUTED; }
.eia-find { position: relative; background: rgba(15,23,42,.6); backdrop-filter: blur(10px); border: 1px solid rgba(30,41,59,.8);
  border-left: 3px solid var(--c); border-radius: 14px; padding: 14px 18px 12px; margin: 12px 0 6px; transition: border-color .2s, transform .2s; }
.eia-find:hover { border-color: rgba(20,184,166,.35); border-left-color: var(--c); }
.eia-find .rank { color: FAINT; font-size: .82rem; margin-right: 8px; }
.eia-find .t { font-size: 1.06rem; font-weight: 600; color: #F8FAFC; }
.eia-find .meta { margin: 8px 0 6px; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; }
.eia-find .s { color: #CBD5E1; font-size: .93rem; max-width: 110ch; }
.eia-ev { border-top: 1px solid rgba(30,41,59,.8); padding: 10px 0 6px; }
.eia-ev:first-child { border-top: none; }
.eia-ev .head { display: flex; flex-wrap: wrap; gap: 6px 14px; align-items: baseline; }
.eia-ev .metric { font-weight: 600; color: TEXT; }
.eia-ev .val { color: TEAL_HI; font-weight: 700; }
.eia-quote { border-left: 3px solid CYAN; background: rgba(2,6,23,.55); padding: 8px 12px; margin: 7px 0 4px; color: #CBD5E1;
  font-size: .88rem; border-radius: 0 10px 10px 0; white-space: pre-wrap; }
.eia-quote.opp { border-left-color: CORAL; }
.eia-src { color: MUTED; font-size: .84rem; }
.eia-disc { position: relative; overflow: hidden; border-radius: 16px; padding: 20px 24px 16px; margin: 6px 0 14px;
  border: 1px solid transparent;
  background: radial-gradient(700px 240px at 0% 0%, rgba(20,184,166,.22), transparent 70%) padding-box,
              radial-gradient(600px 240px at 100% 100%, rgba(139,92,246,.18), transparent 70%) padding-box,
              linear-gradient(rgba(13,20,36,.95), rgba(13,20,36,.95)) padding-box,
              linear-gradient(135deg, rgba(20,184,166,.8), rgba(59,130,246,.4), rgba(139,92,246,.8)) border-box;
  box-shadow: 0 24px 60px -30px rgba(20,184,166,.5); }
.eia-disc .k { color: TEAL_HI; font-size: .72rem; font-weight: 800; letter-spacing: .16em; display: flex; align-items: center; gap: 8px; }
.eia-disc .k::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: MINT;
  box-shadow: 0 0 0 4px rgba(16,185,129,.18), 0 0 12px MINT; animation: eia-pulse 2s ease-in-out infinite; }
@keyframes eia-pulse { 50% { box-shadow: 0 0 0 7px rgba(16,185,129,.0), 0 0 16px MINT; } }
.eia-disc .h { color: #FFFFFF; font-size: 1.45rem; font-weight: 700; line-height: 1.35; margin: 10px 0 12px; max-width: 70ch;
  letter-spacing: -.02em; }
.eia-disc .m { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; }
.eia-why { margin: 0; padding-left: 0; list-style: none; }
.eia-why li { margin: 7px 0; color: #CBD5E1; font-size: .93rem; padding-left: 20px; position: relative; }
.eia-why li::before { content: ""; position: absolute; left: 4px; top: .55em; width: 7px; height: 7px; border-radius: 50%;
  background: CYAN; box-shadow: 0 0 8px CYAN; }
.eia-callout { border-left: 3px solid CYAN; background: rgba(2,6,23,.5); padding: 10px 14px; border-radius: 10px; color: TEXT;
  font-size: .95rem; margin-bottom: 8px; }
div[class*="st-key-panel_kpi"], div[class*="st-key-panel_hdr"] { padding: 8px 12px !important; }
/* Streamlit pulls the last markdown block up with a negative margin; inside cards that pushed boxes past the edge */
div[class*="st-key-panel"] [data-testid="stMarkdownContainer"] > div:last-child,
div[class*="st-key-panel"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
div[class*="st-key-panel"] [data-testid="stElementContainer"]:last-child { margin-bottom: 4px; }
.eia-callout.warn { border-left-color: AMBER; }
.eia-ptable { width: 100%; border-collapse: separate; border-spacing: 0; font-size: .88rem; }
.eia-ptable th { color: FAINT; font-weight: 600; font-size: .72rem; padding: 8px 10px; border-bottom: 1px solid rgba(30,41,59,.9);
  text-align: left; text-transform: uppercase; letter-spacing: .08em; }
.eia-ptable td { padding: 9px 10px; border-bottom: 1px solid rgba(30,41,59,.6); color: #E2E8F0; }
.eia-ptable td:nth-child(2) { color: TEAL_HI; font-weight: 700; }
.eia-ptable tr:hover td { background: rgba(20,184,166,.05); }
.eia-job { padding: 0 2px 6px; }
.eia-job .eia-bar > div { height: 100%; border-radius: 999px; transition: width .6s; }
.eia-job .msgs { height: 6.4em; overflow: hidden; display: flex; flex-direction: column; justify-content: flex-end; }
.eia-job .ln { color: MUTED; font-size: .84rem; line-height: 1.6em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.eia-calc { background: rgba(2,6,23,.5); border: 1px solid rgba(30,41,59,.8); border-radius: 12px; padding: 10px 14px; margin: 8px 0 10px; }
.eia-calc .r { color: TEAL_HI; font-weight: 700; }
.eia-calc code { background: RAISED; color: #CFE3F5; }
.eia-check { padding: 6px 0; border-top: 1px solid rgba(30,41,59,.8); font-size: .9rem; }
.eia-check:first-child { border-top: none; }
.eia-falsify { border: 1px dashed rgba(245,158,11,.6); border-radius: 12px; padding: 10px 14px; color: #FDE68A; background: rgba(245,158,11,.06); }
.eia-mods { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 1.1rem; }
.eia-mod { padding: 12px 16px; background: rgba(15,23,42,.6); border: 1px solid rgba(30,41,59,.8); border-radius: 14px; }
.eia-mod .n { font-weight: 600; margin-bottom: 6px; }
.eia-mod .d { color: MUTED; font-size: .83rem; margin-top: 4px; }
.eia-doc { background: rgba(2,6,23,.6); border: 1px solid rgba(30,41,59,.8); border-radius: 12px; padding: 16px 18px; max-height: 560px;
  overflow: auto; white-space: pre-wrap; font-size: .88rem; line-height: 1.6; color: #CBD5E1; }
.eia-doc mark { background: rgba(245,158,11,.25); color: #FEF3C7; border-bottom: 2px solid AMBER; }
.eia-run { background: rgba(15,23,42,.6); border: 1px solid rgba(30,41,59,.8); border-radius: 12px; padding: 10px 12px; font-size: .85rem; }
.eia-run .co { font-weight: 600; color: TEXT; margin-bottom: 3px; }
.eia-legend { display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: .82rem; color: MUTED; margin: 4px 0 10px; }
.eia-legend i { display: inline-block; width: 18px; height: 3px; margin-right: 6px; vertical-align: middle; border-radius: 3px; }
.eia-table { width: 100%; border-collapse: collapse; font-size: .82rem; }
.eia-table th { text-align: left; color: FAINT; font-weight: 600; border-bottom: 1px solid rgba(30,41,59,.9); padding: 6px 8px;
  font-size: .7rem; text-transform: uppercase; letter-spacing: .08em; }
.eia-table td { padding: 8px; border-bottom: 1px solid rgba(30,41,59,.6); color: #CBD5E1; vertical-align: top; }
.eia-table tr:hover td { background: rgba(20,184,166,.05); }
.eia-status { display: inline-flex; align-items: center; gap: 6px; padding: 2px 9px; border-radius: 999px; font-size: .72rem;
  font-weight: 600; white-space: nowrap; }
.eia-status::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; box-shadow: 0 0 8px currentColor; }
.eia-id { font-family: 'JetBrains Mono', Consolas, monospace; font-size: .76rem; color: #A5B4FC; }
.eia-news { margin: 0; padding-left: 16px; } .eia-news li { font-size: .84rem; color: #CBD5E1; margin: 4px 0; }
.eia-news li::marker { color: CYAN; }

/* AI assistant panel */
.eia-ai-head { display: flex; align-items: center; gap: 10px; margin: 2px 0 10px; }
.eia-ai-head .av { width: 34px; height: 34px; border-radius: 11px; display: grid; place-items: center; flex: 0 0 34px;
  background: linear-gradient(135deg, CYAN, VIOLET); color: #FFFFFF; font-weight: 800; font-size: .8rem;
  box-shadow: 0 0 18px rgba(20,184,166,.5); }
.eia-ai-head .t { font-size: .74rem; font-weight: 800; letter-spacing: .14em; color: #F8FAFC; }
.eia-ai-head .s { font-size: .72rem; color: MINT; display: flex; align-items: center; gap: 6px; }
.eia-ai-head .s::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: MINT; box-shadow: 0 0 8px MINT; }
.eia-msg { display: flex; gap: 8px; margin: 10px 0; align-items: flex-end; }
.eia-msg .b { padding: 10px 13px; font-size: .86rem; line-height: 1.5; max-width: 92%; }
.eia-msg.ai .b { background: rgba(30,41,59,.55); border: 1px solid rgba(51,65,85,.7); color: #E2E8F0; border-radius: 4px 14px 14px 14px; }
.eia-msg.ai .b b { color: TEAL_HI; }
.eia-msg.user { justify-content: flex-end; }
.eia-msg.user .b { background: linear-gradient(135deg, rgba(59,130,246,.85), rgba(139,92,246,.85)); color: #FFFFFF;
  border-radius: 14px 14px 4px 14px; box-shadow: 0 8px 20px -10px rgba(99,102,241,.8); }
.eia-msg .who { font-size: .66rem; color: FAINT; margin: 0 0 3px 2px; }
.eia-msg .cite { display: block; margin-top: 6px; font-size: .72rem; color: MUTED; }
div[class*="st-key-panel_chat"] .stTextInput input { border-radius: 999px !important; padding-left: 16px; }
div[class*="st-key-chatsug"] button { min-height: 30px !important; padding: 2px 10px !important; font-size: .74rem !important;
  border-radius: 999px !important; color: #CBD5E1 !important; background: rgba(30,41,59,.5) !important; font-weight: 500 !important; }
div[class*="st-key-chatsug"] button:hover { color: TEAL_HI !important; }
@media (max-width: 900px) { .eia-mods { grid-template-columns: 1fr; } }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
</style>
"""
for _k, _v in {"FONT": FONT, "PANEL2": PANEL2, "PANEL": PANEL, "BG": BG, "TEXT": TEXT, "MUTED": MUTED,
               "FAINT": FAINT, "TEAL_HI": TEAL_HI, "CYAN": CYAN, "MINT": MINT, "GREEN": GREEN, "AMBER": AMBER, "CORAL": CORAL,
               "RAISED": RAISED, "RULE": RULE, "BLUE": BLUE, "VIOLET": VIOLET, "ICON_CSS": _ICON_CSS}.items():
    CSS = CSS.replace(_k, _v)


# ---- HTML helpers ------------------------------------------------------------------------------------

def chip(text: str, fg: str, bg: str) -> str:
    return f"<span class='eia-chip' style='color:{fg};background:{bg};border-color:{fg}55'>{esc(text)}</span>"


def status_chip(label: str) -> str:
    fg, bg = STATUS.get(label, (MUTED, "#18233A"))
    return chip(label, fg, bg)


def strength_chip(strength: str) -> str:
    fg, bg = STRENGTH_CHIP.get(strength, (MUTED, "#18233A"))
    return chip(f"{strength.capitalize()} evidence", fg, bg)


def module_chip(status: str) -> str:
    text, fg, bg = MODULE_STATUS.get(status, (status or "Not run", MUTED, "#18233A"))
    return chip(text, fg, bg)


def direction_tag(direction: str) -> str:
    text, c = DIRECTION.get(direction, (direction, MUTED))
    return f"<span class='eia-dir' style='color:{c}'>{esc(text)}</span>"


def status_color(label: str) -> str:
    return STATUS.get(label, (MUTED, ""))[0]


def gauge(strength: str, status_label: str) -> str:
    lvl = STRENGTH_LEVEL.get(strength, 0) + 1
    c = status_color(status_label)
    segs = "".join(f"<span class='seg' style='background:{c if i < lvl else RULE}'></span>" for i in range(4))
    return (f"<span class='eia-gauge' title='Evidence strength: {esc(strength)}'>{segs}"
            f"<span class='lbl'>{esc(strength.capitalize())} evidence</span></span>")


def stat_strip(items: list[tuple]) -> str:
    cells = "".join(f"<div class='eia-stat {t}'><div class='v'>{esc(v)}</div><div class='l'>{esc(l)}</div>"
                    + (f"<div class='n'>{esc(n)}</div>" if n else "") + "</div>" for v, l, n, t in items)
    return f"<div class='eia-stats'>{cells}</div>"


def page_header(title: str, subtitle: str = "") -> str:
    return f"<div class='eia-title'>{esc(title)}</div>" + (f"<div class='eia-sub'>{esc(subtitle)}</div>" if subtitle else "")


def section(title: str) -> str:
    return f"<div class='eia-h'>{esc(title)}</div>"


def ptitle(title: str, right: str = "") -> str:
    """Panel title; `right` is trusted HTML (a link or a figure)."""
    return f"<div class='eia-ptitle'><span>{esc(title)}</span><span class='right'>{right}</span></div>"


def highlight(text: str, passage: str) -> str:
    out = esc(text)
    for line in sorted({l.strip() for l in (passage or "").splitlines() if len(l.strip()) >= 12}, key=len, reverse=True):
        e = esc(line)
        if e in out:
            out = out.replace(e, f"<mark>{e}</mark>")
    return out


def sparkline(values: list[float], color: str = CYAN, w: int = 150, h: int = 40, fill: bool = True) -> str:
    """Inline SVG line from real values; empty string when fewer than two points."""
    import uuid
    v = [x for x in values if x is not None]
    if len(v) < 2:
        return ""
    gid = "s" + uuid.uuid4().hex[:8]
    lo, hi = min(v), max(v)
    rng = (hi - lo) or 1.0
    pts = [(i * (w - 8) / (len(v) - 1) + 4, h - 5 - (x - lo) / rng * (h - 12)) for i, x in enumerate(v)]
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = (f"<defs><linearGradient id='{gid}' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='{color}' "
            f"stop-opacity='.35'/><stop offset='1' stop-color='{color}' stop-opacity='0'/></linearGradient></defs>"
            f"<polygon points='4,{h} {d} {w - 4},{h}' fill='url(#{gid})'/>") if fill else ""
    lx, ly = pts[-1]
    return (f"<svg width='100%' height='{h}' viewBox='0 0 {w} {h}' preserveAspectRatio='none'>{area}"
            f"<polyline points='{d}' fill='none' stroke='{color}' stroke-width='2' stroke-linejoin='round' "
            f"stroke-linecap='round' vector-effect='non-scaling-stroke'/>"
            f"<circle cx='{lx:.1f}' cy='{ly:.1f}' r='5' fill='{color}' opacity='.25'/>"
            f"<circle cx='{lx:.1f}' cy='{ly:.1f}' r='2.6' fill='{color}'/></svg>")


def minibars(values: list[float], color: str = BLUE, w: int = 150, h: int = 40) -> str:
    v = [x for x in values if x is not None]
    if not v:
        return ""
    hi = max(v) or 1.0
    bw = (w - 4) / len(v)
    bars = "".join(f"<rect x='{2 + i * bw + bw * .18:.1f}' y='{h - x / hi * (h - 4):.1f}' width='{bw * .64:.1f}' "
                   f"height='{x / hi * (h - 4):.1f}' rx='1.5' fill='{color}' opacity='{.45 + .55 * (i + 1) / len(v):.2f}'/>"
                   for i, x in enumerate(v))
    return f"<svg width='100%' height='{h}' viewBox='0 0 {w} {h}' preserveAspectRatio='none'>{bars}</svg>"


def ring(pct: float | None, color: str = GREEN, size: int = 104, color2: str | None = None) -> str:
    """Circular gauge; a gradient arc with a soft glow when color2 is given."""
    import uuid
    gid = "g" + uuid.uuid4().hex[:8]
    r, c = 40, 2 * 3.14159 * 40
    p = max(0.0, min(100.0, pct or 0))
    label = f"{p:.0f}%" if pct is not None else "n/a"
    stroke = f"url(#{gid})" if color2 else color
    defs = (f"<defs><linearGradient id='{gid}' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='{color}'/>"
            f"<stop offset='1' stop-color='{color2}'/></linearGradient><filter id='{gid}f'><feGaussianBlur stdDeviation='2.2'/>"
            f"</filter></defs>") if color2 else ""
    glow = (f"<circle cx='50' cy='50' r='{r}' stroke='{stroke}' stroke-width='10' fill='none' stroke-linecap='round' "
            f"stroke-dasharray='{c * p / 100:.1f} {c:.1f}' transform='rotate(-90 50 50)' filter='url(#{gid}f)' opacity='.7'/>"
            if color2 else "")
    return (f"<svg width='{size}' height='{size}' viewBox='0 0 100 100'>{defs}"
            f"<circle cx='50' cy='50' r='{r}' stroke='rgba(51,65,85,.55)' stroke-width='10' fill='none'/>{glow}"
            f"<circle cx='50' cy='50' r='{r}' stroke='{stroke}' stroke-width='10' fill='none' stroke-linecap='round' "
            f"stroke-dasharray='{c * p / 100:.1f} {c:.1f}' transform='rotate(-90 50 50)'/>"
            f"<text x='50' y='57' text-anchor='middle' font-size='19' font-weight='700' fill='#FFFFFF' "
            f"font-family='Inter, sans-serif'>{label}</text></svg>")


SKYLINE = (  # generic power-station silhouette (cooling towers, stack, pylons), drawn for this app
    "<svg class='sky' viewBox='0 0 600 260' preserveAspectRatio='xMaxYMax meet'>"
    "<defs><linearGradient id='g' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#0B1424' stop-opacity='.2'/>"
    "<stop offset='1' stop-color='#05080F'/></linearGradient></defs>"
    "<path d='M300 260 L318 120 Q310 95 322 80 L382 80 Q394 95 386 120 L404 260 Z' fill='url(#g)'/>"
    "<path d='M410 260 L430 105 Q421 76 435 60 L507 60 Q521 76 512 105 L532 260 Z' fill='url(#g)'/>"
    "<rect x='548' y='30' width='12' height='230' fill='#05080F'/>"
    "<path d='M330 70 Q340 40 330 10 M460 52 Q472 22 462 -8' stroke='#C9D5E6' stroke-opacity='.18' stroke-width='14' fill='none' stroke-linecap='round'/>"
    "<path d='M200 260 L220 170 L240 260 M206 230 L234 230 M212 200 L228 200 M190 175 L250 175' stroke='#05080F' stroke-width='3' fill='none'/>"
    "<rect x='0' y='238' width='600' height='22' fill='#05080F'/></svg>")

CHART_FONT = "Inter, Segoe UI, system-ui, sans-serif"
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#C9D5E6", family=CHART_FONT, size=11),
    margin=dict(l=12, r=12, t=36, b=12), title_font=dict(size=13, color=TEXT, family=CHART_FONT),
    xaxis=dict(gridcolor="rgba(0,0,0,0)", zerolinecolor=RULE, linecolor="rgba(51,65,85,.8)", automargin=True, ticks="",
               ticklen=0, tickfont=dict(color=MUTED, size=10, family=CHART_FONT)),
    yaxis=dict(gridcolor="rgba(51,65,85,.45)", griddash="dot", zerolinecolor="#2A3B5A", linecolor="rgba(0,0,0,0)", automargin=True,
               tickfont=dict(color=MUTED, size=10, family=CHART_FONT), title_font=dict(color=MUTED, size=10)),
    bargap=0.42, hovermode="x unified",
    legend=dict(orientation="h", y=1.12, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=10, family=CHART_FONT)),
    hoverlabel=dict(bgcolor="rgba(15,23,42,.95)", bordercolor=CYAN, font=dict(color=TEXT, family=CHART_FONT, size=11)))
PLOTLY_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}


def nav_css(slugs: list[str], active: str) -> str:
    """Sidebar navigation drawn as buttons (stable across Streamlit versions): icon, left-aligned label,
    highlighted active page. Uses the st-key-<key> class Streamlit adds to keyed widgets."""
    rules = []
    for i, slug in enumerate(slugs):
        url = _icon_url(ICONS[i % len(ICONS)])
        rules.append(f'.st-key-nav_{slug} button::before{{-webkit-mask-image:url("{url}");mask-image:url("{url}");}}')
    base = (
        '[class*="st-key-nav_"] { margin: 0 !important; width: 100% !important; }'
        '[class*="st-key-nav_"] .stButton, [class*="st-key-nav_"] button { width: 100% !important; }'
        '[class*="st-key-nav_"] button { justify-content: flex-start !important; gap: 12px; padding: 8px 12px !important;'
        ' min-height: 40px !important; border: 1px solid transparent !important; background: transparent !important;'
        ' border-radius: 12px !important; color: #94A3B8 !important; font-weight: 500 !important; box-shadow: none !important;'
        ' transform: none !important; }'
        '[class*="st-key-nav_"] button:hover { background: rgba(30,41,59,.55) !important; color: #F8FAFC !important; }'
        '[class*="st-key-nav_"] button > div, [class*="st-key-nav_"] button p { text-align: left !important;'
        ' justify-content: flex-start !important; margin: 0 !important; font-size: .9rem !important; }'
        '[class*="st-key-nav_"] button::before { content: ""; width: 18px; height: 18px; flex: 0 0 18px;'
        ' background-color: currentColor; -webkit-mask-repeat: no-repeat; mask-repeat: no-repeat;'
        ' -webkit-mask-size: contain; mask-size: contain; }'
        f'.st-key-nav_{active} button {{ background: linear-gradient(90deg, rgba(20,184,166,.22), rgba(59,130,246,.08)) !important;'
        f' border-color: rgba(20,184,166,.35) !important; color: #FFFFFF !important;'
        f' box-shadow: 0 0 22px -8px {CYAN} !important; }}'
        f'.st-key-nav_{active} button::before {{ background-color: {TEAL_HI} !important; }}'
        'section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.15rem; }')
    return "<style>" + base + "".join(rules) + "</style>"
