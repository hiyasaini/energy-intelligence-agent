"""Visual system: deep navy panels, cyan primary, green opportunity, amber caution, coral risk, violet links.
Layout follows the product mockup: icon sidebar, top search bar, company header with KPI tiles, panel grid."""
from __future__ import annotations

import html as _html

BG = "#070D1A"
PANEL = "#0D1628"
PANEL2 = "#101B31"
RAISED = "#16233B"
RULE = "#1E2D48"
TEXT = "#E6EDF7"
MUTED = "#93A4BE"
FAINT = "#62748F"
CYAN = "#22C7E8"
BLUE = "#3B82F6"
GREEN = "#22C55E"
MINT = GREEN
AMBER = "#F59E0B"
CORAL = "#F25F5C"
VIOLET = "#8B5CF6"
ORANGE = "#F97316"

STATUS = {
    "Supported": (CYAN, "#062B36"),
    "Pending counter-check": (AMBER, "#33240A"),
    "Unresolved": (AMBER, "#33240A"),
    "Weakened": (AMBER, "#2E220B"),
    "Rejected": (CORAL, "#36161A"),
    "Insufficient evidence": (MUTED, "#18233A"),
}
DIRECTION = {"risk": ("Risk", CORAL), "opportunity": ("Opportunity", GREEN), "neutral": ("Observation", MUTED)}
MODULE_STATUS = {"ok": ("Sufficient data", CYAN, "#062B36"), "partial": ("Partial data", AMBER, "#33240A"),
                 "insufficient_data": ("Insufficient data", MUTED, "#18233A"), "error": ("Module error", CORAL, "#36161A")}
STRENGTH_LEVEL = {"insufficient": 0, "weak": 1, "moderate": 2, "strong": 3}
STRENGTH_CHIP = {"strong": (GREEN, "#0B2A18"), "moderate": (AMBER, "#33240A"), "weak": (ORANGE, "#33190A"),
                 "insufficient": (MUTED, "#18233A")}
# Chart palette: categorical hues stepped for a dark surface and checked for colour-blind separation.
# Used in fixed order (never cycled); UI chrome keeps the brand cyan above.
C_BLUE, C_ORANGE, C_AQUA, C_YELLOW = "#3987E5", "#D95926", "#199E70", "#C98500"
C_MAGENTA, C_GREEN, C_VIOLET, C_RED = "#D55181", "#2E9E3E", "#9085E9", "#E66767"
C_GREY = "#7D8BA0"
SERIES_COLORS = [C_BLUE, C_ORANGE, C_AQUA, C_YELLOW, C_MAGENTA, C_GREEN, C_VIOLET, C_RED]
SOURCE_COLORS = {"Coal": C_GREY, "Solar": C_YELLOW, "Wind": C_AQUA, "Hydro": C_BLUE, "Gas": C_ORANGE,
                 "Nuclear": C_VIOLET}

FONT = "'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"


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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, .stApp, [class*="css"], button, input, textarea { font-family: FONT; }
.stApp { background: radial-gradient(1200px 600px at 70% -10%, #0F2240 0%, BG 55%) fixed, BG; color: TEXT; }
/* keep Streamlit's header (it holds the button that reopens a collapsed sidebar); hide only clutter */
footer, [data-testid="stDecoration"], [data-testid="stStatusWidget"], [data-testid="stAppDeployButton"],
.stDeployButton, #MainMenu { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"],
[data-testid="stSidebarCollapseButton"] { visibility: visible !important; display: flex !important; opacity: 1 !important;
  z-index: 1000; }
[data-testid="stSidebarCollapsedControl"] button, [data-testid="stExpandSidebarButton"] {
  background: #0E3350 !important; border: 1px solid #22C7E8 !important; border-radius: 8px !important;
  color: #FFFFFF !important; }
.block-container, [data-testid="stMainBlockContainer"] { padding-top: 2.6rem !important; padding-bottom: 3rem; max-width: 100% !important; padding-left: 2.2rem !important; padding-right: 2.2rem !important; }
p, li, span, div { font-variant-numeric: tabular-nums; }
a { color: CYAN !important; text-decoration: none !important; }
a:hover { text-decoration: underline !important; }
:focus-visible { outline: 2px solid CYAN !important; outline-offset: 2px; }
h1, h2, h3, h4 { color: TEXT !important; }

/* sidebar */
section[data-testid="stSidebar"] { background: #060B16; border-right: 1px solid RULE; }
section[data-testid="stSidebar"][aria-expanded="true"] { min-width: 250px; }
section[data-testid="stSidebar"][aria-expanded="false"] { min-width: 0 !important; width: 0 !important; max-width: 0 !important;
  border-right: none; overflow: hidden; }
section[data-testid="stSidebar"] .block-container, section[data-testid="stSidebar"] [data-testid="stSidebarContent"] { padding-top: .6rem; }
section[data-testid="stSidebar"] div[role="radiogroup"] { gap: 2px; }
section[data-testid="stSidebar"] div[role="radiogroup"] label {
  display: flex; align-items: center; gap: 12px; padding: 9px 12px; border-radius: 8px; margin: 0; width: 100%;
  cursor: pointer; color: #C3CEDF; border: 1px solid transparent; }
section[data-testid="stSidebar"] div[role="radiogroup"] label::before {
  content: ""; width: 18px; height: 18px; flex: 0 0 18px; background-color: currentColor;
  -webkit-mask-repeat: no-repeat; mask-repeat: no-repeat; -webkit-mask-size: contain; mask-size: contain; }
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover { background: #0E1A2F; color: TEXT; }
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
  background: linear-gradient(90deg, #0E3350, #0C2440); border-color: #1D4A73; color: #FFFFFF; }
section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-of-type:not(:last-child),
section[data-testid="stSidebar"] div[role="radiogroup"] label input[type="radio"] + div:not(:last-child),
section[data-testid="stSidebar"] div[role="radiogroup"] label [data-baseweb="radio"] { display: none !important; }
section[data-testid="stSidebar"] div[role="radiogroup"] p { font-size: .93rem; }
ICON_CSS

/* brand */
.eia-brand { display: flex; align-items: center; gap: 10px; margin: 2px 0 18px; }
.eia-brand .mark { width: 34px; height: 34px; border-radius: 50%; flex: 0 0 34px;
  background: conic-gradient(from 200deg, CYAN, GREEN, BLUE, CYAN); display: grid; place-items: center; }
.eia-brand .mark span { width: 22px; height: 22px; border-radius: 50%; background: #060B16; display: grid; place-items: center;
  color: CYAN; font-weight: 700; font-size: 13px; }
.eia-brand .name { font-weight: 700; font-size: .9rem; letter-spacing: .02em; color: #FFFFFF; line-height: 1.1; }
.eia-brand .ai { display: inline-block; margin-left: 6px; padding: 0 6px; border-radius: 4px; background: #1D3A8A;
  color: #C7D7FF; font-size: .7rem; font-weight: 700; vertical-align: 2px; }
.eia-brand .tag { color: FAINT; font-size: .62rem; letter-spacing: .06em; margin-top: 3px; white-space: nowrap; }

/* panels: bordered containers keyed panel_* */
div[class*="st-key-panel"] { background: linear-gradient(180deg, PANEL2, PANEL); border: 1px solid RULE !important;
  border-radius: 12px; padding: 4px 6px; }
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div[class*="st-key-panel"]) { border: none !important; }
.eia-ptitle { display: flex; justify-content: space-between; align-items: center; font-weight: 600; font-size: 1.0rem;
  color: TEXT; margin: 2px 0 10px; }
.eia-ptitle .right { font-size: .82rem; font-weight: 500; }
.eia-ptitle .big { color: CYAN; font-size: 1.15rem; font-weight: 700; }

/* buttons, inputs */
.stButton > button, .stDownloadButton > button, [data-testid="stPopover"] button {
  border-radius: 8px; border: 1px solid #2A3D5E; background: #0F1B30; color: TEXT; font-weight: 600; min-height: 40px; }
.stButton > button:hover, .stDownloadButton > button:hover { border-color: CYAN; color: CYAN; }
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
  background: linear-gradient(90deg, #22C7E8, #1FA9F0); color: #03202B; border: none; }
.stButton > button[kind="primary"]:hover { filter: brightness(1.08); color: #03202B; }
.stTextInput input { background: #0B1527 !important; border: 1px solid #22355A !important; border-radius: 8px !important;
  color: TEXT !important; min-height: 42px; }
div[data-testid="stExpander"] { background: PANEL; border: 1px solid RULE; border-radius: 10px; }
.stTabs [data-baseweb="tab-list"] { gap: 2px; border-bottom: 1px solid RULE; }
.stTabs [data-baseweb="tab"] { padding: 9px 18px; color: MUTED; font-weight: 500; }
.stTabs [aria-selected="true"] { color: #FFFFFF !important; background: linear-gradient(180deg, #123A63, #0D2747);
  border-radius: 8px 8px 0 0; }
div[data-testid="stDataFrame"] { border: 1px solid RULE; border-radius: 10px; }
[data-testid="stSegmentedControl"] button, div[data-baseweb="button-group"] button { border-radius: 7px !important; }

/* company header */
.eia-co { display: flex; gap: 16px; align-items: center; padding: 6px 8px; height: 100%; }
.eia-co .logo { width: 68px; height: 68px; border-radius: 12px; background: #F4F7FB; display: grid; place-items: center;
  color: #0B3B8C; font-weight: 800; font-size: 1.3rem; letter-spacing: .02em; flex: 0 0 68px; }
.eia-co .n { font-size: 1.35rem; font-weight: 700; color: #FFFFFF; line-height: 1.15; overflow: hidden;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.eia-co > div:last-child { min-width: 0; }
.eia-co .ids { color: MUTED; font-size: .9rem; margin: 4px 0 8px; }
.eia-tag { display: inline-block; padding: 3px 10px; margin: 0 6px 4px 0; border: 1px solid #2A3D5E; border-radius: 6px;
  background: #0F1B30; color: #C3CEDF; font-size: .78rem; }

/* KPI tiles */
.eia-kpi { padding: 12px 16px 10px; min-height: 118px; }
.eia-kpi .v { font-size: 1.22rem; font-weight: 700; color: #FFFFFF; display: flex; justify-content: space-between;
  align-items: baseline; gap: 6px; white-space: nowrap; }
.eia-kpi .ch { font-size: .82rem; font-weight: 600; }
.eia-kpi .l { color: MUTED; font-size: .82rem; margin: 2px 0 6px; }
.eia-kpi .src { color: FAINT; font-size: .7rem; }
.eia-meter { height: 8px; border-radius: 6px; background: #1A2842; overflow: hidden; margin-top: 10px; }
.eia-meter > div { height: 100%; border-radius: 6px; }

/* hero */
.eia-hero { position: relative; border-radius: 10px; overflow: hidden; padding: 20px 22px 14px; min-height: 196px;
  background: linear-gradient(100deg, rgba(8,16,32,.97) 0%, rgba(8,16,32,.85) 45%, rgba(8,16,32,.35) 100%),
              linear-gradient(180deg, #1B2C4C 0%, #3A3550 55%, #8A5A3C 100%); }
.eia-hero svg.sky { position: absolute; right: 0; bottom: 0; height: 100%; opacity: .9; }
.eia-hero .chip { display: inline-flex; gap: 6px; align-items: center; padding: 3px 10px; border-radius: 6px;
  background: #0B2A18; border: 1px solid #1F6B3B; color: #4ADE80; font-size: .74rem; font-weight: 700; letter-spacing: .04em; }
.eia-hero .t { position: relative; font-size: 1.75rem; font-weight: 700; color: #FFFFFF; margin: 12px 0 6px; line-height: 1.2; }
.eia-hero .s { position: relative; color: #C9D5E6; font-size: .95rem; }
.eia-hero .s b { color: CYAN; } .eia-hero .s b.g { color: GREEN; }
.eia-hero .u { position: relative; color: MUTED; font-size: .8rem; margin-top: 6px; }

/* progress + sources */
.eia-bar { height: 8px; border-radius: 6px; background: #1A2842; margin: 0 0 12px; overflow: hidden; }
.eia-bar > div { height: 100%; background: linear-gradient(90deg, CYAN, #38BDF8); border-radius: 6px; }
.eia-step { display: flex; align-items: center; gap: 10px; padding: 5px 0; font-size: .88rem; color: #C9D5E6; }
.eia-step .ok { width: 18px; height: 18px; border-radius: 50%; display: grid; place-items: center; flex: 0 0 18px;
  font-size: 11px; font-weight: 800; }
.eia-step .v { margin-left: auto; color: TEXT; font-weight: 600; white-space: nowrap; }
.eia-srow { display: flex; align-items: center; gap: 10px; padding: 5px 0; font-size: .88rem; color: #C9D5E6; }
.eia-srow .ic { width: 18px; height: 18px; border-radius: 4px; border: 1.5px solid MUTED; flex: 0 0 18px; }
.eia-srow .v { margin-left: auto; font-weight: 600; color: TEXT; }

/* highlight tiles */
.eia-hl { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.eia-hl a.tile { display: block; border-radius: 10px; padding: 12px 16px; min-height: 84px; border: 1px solid;
  text-decoration: none !important; position: relative; }
.eia-hl a.tile:hover { filter: brightness(1.15); }
.eia-hl .n { font-size: 1.9rem; font-weight: 700; line-height: 1.1; }
.eia-hl .l { font-size: .84rem; margin-top: 6px; }
.eia-hl .ic { position: absolute; right: 14px; top: 14px; font-size: 1.1rem; opacity: .9; }
@media (max-width: 1100px) { .eia-hl { grid-template-columns: repeat(2, 1fr); } }

/* confidence ring + legend */
.eia-ring { display: flex; gap: 18px; align-items: center; }
.eia-ring .lg div { display: flex; align-items: center; gap: 8px; color: #C9D5E6; font-size: .86rem; padding: 3px 0; }
.eia-ring .lg i { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.eia-outlook { display: flex; gap: 14px; align-items: flex-start; }
.eia-outlook .badge { width: 42px; height: 42px; border-radius: 50%; display: grid; place-items: center; flex: 0 0 42px;
  border: 2px solid; font-size: 1.1rem; }
.eia-outlook .h { font-weight: 700; font-size: 1.02rem; margin-bottom: 4px; }
.eia-outlook .p { color: MUTED; font-size: .86rem; line-height: 1.45; }

/* lists */
.eia-find-li { display: flex; gap: 12px; align-items: flex-start; padding: 8px 0; border-bottom: 1px solid RULE; }
.eia-find-li:last-child { border-bottom: none; }
.eia-find-li .num { width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; flex: 0 0 26px;
  font-weight: 700; color: #06101F; font-size: .85rem; }
.eia-find-li .t { font-weight: 600; color: CYAN; font-size: .92rem; }
.eia-find-li .d { color: MUTED; font-size: .8rem; margin-top: 2px; }
.eia-find-li .chip { margin-left: auto; }
.eia-tl { position: relative; }
.eia-tl .row { display: flex; gap: 12px; padding: 6px 0; font-size: .84rem; align-items: flex-start; }
.eia-tl .dt { width: 74px; flex: 0 0 74px; color: CYAN; font-weight: 600; }
.eia-tl .dot { width: 9px; height: 9px; border-radius: 50%; background: CYAN; margin-top: 5px; flex: 0 0 9px;
  box-shadow: 0 0 0 3px #0B2C40; }
.eia-tl .tx { color: #C9D5E6; }
.eia-mix .row { display: flex; gap: 10px; align-items: center; font-size: .86rem; color: #C9D5E6; padding: 4px 0; }
.eia-mix i { width: 10px; height: 10px; border-radius: 50%; }
.eia-mix .v { margin-left: auto; font-weight: 600; color: TEXT; }

/* shared pieces (other pages) */
.eia-title { font-size: 1.7rem; font-weight: 700; color: #FFFFFF; margin: .3rem 0 .25rem; }
.eia-sub { color: MUTED; font-size: .95rem; max-width: 80ch; margin: 0 0 1.1rem; }
.eia-h { font-size: 1.1rem; font-weight: 600; margin: 1.3rem 0 .5rem; color: TEXT; }
.eia-muted { color: MUTED; font-size: .88rem; }
.eia-faint { color: FAINT; font-size: .8rem; }
.eia-empty { color: MUTED; font-size: .88rem; padding: 18px 4px; }
.eia-banner { padding: 10px 14px; border-radius: 10px; margin-bottom: 1rem; font-size: .92rem; }
.eia-banner.demo { background: #2B1F07; border: 1px solid #B7791F; color: #FDE7B0; }
.eia-banner.live { background: PANEL; border: 1px solid RULE; color: TEXT; display: flex; gap: 14px; flex-wrap: wrap; }
.eia-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); border: 1px solid RULE;
  border-radius: 12px; background: PANEL; margin: .4rem 0 1.1rem; }
.eia-stat { padding: 14px 18px; border-right: 1px solid RULE; }
.eia-stat:last-child { border-right: none; }
.eia-stat .v { font-size: 1.6rem; font-weight: 700; color: TEXT; }
.eia-stat .l { color: MUTED; font-size: .84rem; margin-top: 4px; }
.eia-stat .n { color: FAINT; font-size: .78rem; }
.eia-stat.accent .v { color: CYAN; } .eia-stat.warn .v { color: AMBER; } .eia-stat.bad .v { color: CORAL; }
.eia-chip { display: inline-block; padding: 2px 9px; border-radius: 6px; font-size: .76rem; font-weight: 600;
  margin: 0 6px 4px 0; border: 1px solid transparent; white-space: nowrap; }
.eia-dir { font-size: .8rem; font-weight: 600; margin-right: 10px; }
.eia-gauge { display: inline-flex; align-items: center; gap: 8px; vertical-align: middle; }
.eia-gauge .seg { display: inline-block; width: 20px; height: 6px; border-radius: 2px; background: RULE; margin-right: 3px; }
.eia-gauge .lbl { font-size: .8rem; color: MUTED; }
.eia-find { background: PANEL; border: 1px solid RULE; border-left: 4px solid var(--c); border-radius: 10px;
  padding: 14px 18px 12px; margin: 12px 0 6px; }
.eia-find .rank { color: FAINT; font-size: .85rem; margin-right: 8px; }
.eia-find .t { font-size: 1.08rem; font-weight: 600; color: #FFFFFF; }
.eia-find .meta { margin: 8px 0 6px; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; }
.eia-find .s { color: #C9D5E6; font-size: .93rem; max-width: 110ch; }
.eia-ev { border-top: 1px solid RULE; padding: 10px 0 6px; }
.eia-ev:first-child { border-top: none; }
.eia-ev .head { display: flex; flex-wrap: wrap; gap: 6px 14px; align-items: baseline; }
.eia-ev .metric { font-weight: 600; color: TEXT; }
.eia-ev .val { color: CYAN; font-weight: 700; }
.eia-quote { border-left: 3px solid CYAN; background: #0A1424; padding: 7px 12px; margin: 7px 0 4px; color: #C9D5E6;
  font-size: .88rem; border-radius: 0 6px 6px 0; white-space: pre-wrap; }
.eia-quote.opp { border-left-color: CORAL; }
.eia-src { color: MUTED; font-size: .84rem; }
.eia-job { padding: 0 2px 6px; }
.eia-job .eia-bar > div { height: 100%; background: CYAN; border-radius: 6px; transition: width .6s; }
.eia-job .msgs { height: 6.4em; overflow: hidden; display: flex; flex-direction: column; justify-content: flex-end; }
.eia-job .ln { color: MUTED; font-size: .84rem; line-height: 1.6em; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }
.eia-calc { background: #0A1424; border: 1px solid RULE; border-radius: 8px; padding: 10px 14px; margin: 8px 0; }
.eia-calc .r { color: CYAN; font-weight: 700; }
.eia-calc code { background: RAISED; color: #CFE3F5; }
.eia-check { padding: 6px 0; border-top: 1px solid RULE; font-size: .9rem; }
.eia-check:first-child { border-top: none; }
.eia-falsify { border: 1px dashed #B7791F; border-radius: 8px; padding: 10px 14px; color: #FDE7B0; background: #1E1606; }
.eia-mods { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: RULE; border: 1px solid RULE;
  border-radius: 12px; overflow: hidden; margin-bottom: 1.1rem; }
.eia-mod { padding: 12px 16px; background: PANEL; }
.eia-mod .n { font-weight: 600; margin-bottom: 6px; }
.eia-mod .d { color: MUTED; font-size: .83rem; margin-top: 4px; }
.eia-doc { background: #060C18; border: 1px solid RULE; border-radius: 10px; padding: 16px 18px; max-height: 560px;
  overflow: auto; white-space: pre-wrap; font-size: .88rem; line-height: 1.55; color: #C9D5E6; }
.eia-doc mark { background: #F59E0B40; color: #FFF3D6; border-bottom: 2px solid AMBER; }
.eia-run { background: PANEL; border: 1px solid RULE; border-radius: 10px; padding: 10px 12px; font-size: .85rem; }
.eia-run .co { font-weight: 600; color: TEXT; margin-bottom: 3px; }
.eia-legend { display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: .84rem; color: MUTED; margin: 4px 0 10px; }
.eia-legend i { display: inline-block; width: 18px; height: 3px; margin-right: 6px; vertical-align: middle; }
.eia-table { width: 100%; border-collapse: collapse; font-size: .8rem; }
.eia-table th { text-align: left; color: MUTED; font-weight: 500; border-bottom: 1px solid RULE; padding: 4px 6px; }
.eia-table td { padding: 5px 6px; border-bottom: 1px solid RULE; color: #C9D5E6; vertical-align: top; }
.eia-news { margin: 0; padding-left: 16px; } .eia-news li { font-size: .84rem; color: #C9D5E6; margin: 4px 0; }
@media (max-width: 900px) { .eia-mods { grid-template-columns: 1fr; } }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
</style>
"""
for _k, _v in {"FONT": FONT, "PANEL2": PANEL2, "PANEL": PANEL, "BG": BG, "TEXT": TEXT, "MUTED": MUTED,
               "FAINT": FAINT, "CYAN": CYAN, "GREEN": GREEN, "AMBER": AMBER, "CORAL": CORAL, "RAISED": RAISED,
               "RULE": RULE, "BLUE": BLUE, "ICON_CSS": _ICON_CSS}.items():
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
    v = [x for x in values if x is not None]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    rng = (hi - lo) or 1.0
    pts = [(i * (w - 6) / (len(v) - 1) + 3, h - 4 - (x - lo) / rng * (h - 10)) for i, x in enumerate(v)]
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"<polygon points='3,{h} {d} {w - 3},{h}' fill='{color}' opacity='.12'/>" if fill else ""
    lx, ly = pts[-1]
    return (f"<svg width='100%' height='{h}' viewBox='0 0 {w} {h}' preserveAspectRatio='none'>{area}"
            f"<polyline points='{d}' fill='none' stroke='{color}' stroke-width='2' stroke-linejoin='round'/>"
            f"<circle cx='{lx:.1f}' cy='{ly:.1f}' r='3' fill='{color}'/></svg>")


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


def ring(pct: float | None, color: str = GREEN, size: int = 104) -> str:
    r, c = 40, 2 * 3.14159 * 40
    p = max(0.0, min(100.0, pct or 0))
    label = f"{p:.0f}%" if pct is not None else "n/a"
    return (f"<svg width='{size}' height='{size}' viewBox='0 0 100 100'>"
            f"<circle cx='50' cy='50' r='{r}' stroke='{RULE}' stroke-width='10' fill='none'/>"
            f"<circle cx='50' cy='50' r='{r}' stroke='{color}' stroke-width='10' fill='none' stroke-linecap='round' "
            f"stroke-dasharray='{c * p / 100:.1f} {c:.1f}' transform='rotate(-90 50 50)'/>"
            f"<text x='50' y='56' text-anchor='middle' font-size='19' font-weight='700' fill='#FFFFFF' "
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

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#C9D5E6", family="Inter, sans-serif", size=12),
    margin=dict(l=12, r=12, t=36, b=12), title_font=dict(size=15, color=TEXT),
    xaxis=dict(gridcolor="rgba(0,0,0,0)", zerolinecolor=RULE, linecolor=RULE, automargin=True,
               tickfont=dict(color=MUTED, size=11)),
    yaxis=dict(gridcolor="#18253D", zerolinecolor="#2A3B5A", linecolor="rgba(0,0,0,0)", automargin=True,
               tickfont=dict(color=MUTED, size=11), title_font=dict(color=MUTED, size=11)),
    bargap=0.42, hovermode="x unified",
    legend=dict(orientation="h", y=1.12, x=0, bgcolor="rgba(0,0,0,0)"),
    hoverlabel=dict(bgcolor=RAISED, bordercolor=RULE, font=dict(color=TEXT)))
PLOTLY_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}


def nav_css(slugs: list[str], active: str) -> str:
    """Sidebar navigation drawn as buttons (stable across Streamlit versions): icon, left-aligned label,
    highlighted active page. Uses the st-key-<key> class Streamlit adds to keyed widgets."""
    rules = []
    for i, slug in enumerate(slugs):
        url = _icon_url(ICONS[i % len(ICONS)])
        rules.append(f'.st-key-nav_{slug} button::before{{-webkit-mask-image:url("{url}");mask-image:url("{url}");}}')
    base = (
        '[class*="st-key-nav_"] { margin: 0 !important; }'
        '[class*="st-key-nav_"] .stButton, [class*="st-key-nav_"] button { width: 100% !important; }'
        '[class*="st-key-nav_"] button { justify-content: flex-start !important; gap: 12px; padding: 8px 12px !important;'
        ' min-height: 40px !important; border: 1px solid transparent !important; background: transparent !important;'
        ' color: #C3CEDF !important; font-weight: 500 !important; box-shadow: none !important; }'
        '[class*="st-key-nav_"] button:hover { background: #0E1A2F !important; color: #FFFFFF !important; }'
        '[class*="st-key-nav_"] button > div, [class*="st-key-nav_"] button p { text-align: left !important;'
        ' justify-content: flex-start !important; margin: 0 !important; }'
        '[class*="st-key-nav_"] button::before { content: ""; width: 18px; height: 18px; flex: 0 0 18px;'
        ' background-color: currentColor; -webkit-mask-repeat: no-repeat; mask-repeat: no-repeat;'
        ' -webkit-mask-size: contain; mask-size: contain; }'
        f'.st-key-nav_{active} button {{ background: linear-gradient(90deg, #0E3350, #0C2440) !important;'
        ' border-color: #1D4A73 !important; color: #FFFFFF !important; }'
        'section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.15rem; }')
    return "<style>" + base + "".join(rules) + "</style>"
