"""BRICS Climate Intelligence Platform — Streamlit dashboard (Anoushka)

Reference implementation by Sarthak (2026-09-21) — restyled iteration 2.

Aesthetic: "stylistic minimalism" — opencode (terminal-native restraint) ·
ventriloc (data-centric hierarchy) · hermes (quiet premium surfaces).
Dark, muted, monospaced data, generous whitespace. Zero emojis.

FONT GLOSSARY — control surface (rev 2)
----------------------------------------
  Inter          -> everything textual: body, headings, hero numerals
                    (weights 400/500/600/700 — crisp, professional)
  JetBrains Mono -> ALL data, labels, eyebrows, captions
  Gencha         -> reserved alternate (elegant sans) — not currently active
  SCRAPPED: Oscan Expanded + Molecule (legibility failures) and Ampere
  (CDN unavailable) — do not reintroduce without hosting them properly.
  Every stack falls back to system-ui / ui-monospace.

THEME SYSTEM (rev 2.2)
----------------------
  Eight muted, cohesive dark palettes live in THEMES{} below and are swapped at
  runtime through CSS custom properties — control sits at the bottom of the
  sidebar (APPEARANCE). Reference principle: a quiet neutral base carries the
  surface, one restrained accent carries emphasis; nothing saturated.
  AQI category colours are deliberately theme-invariant: colour must mean the
  same thing in every palette.

RULES (from work-division.md)
-----------------------------
  - NEVER call external APIs from the frontend. ONLY Sujal's endpoints.
  - Parse Pydantic shapes exactly as the backend serves them.
  - Handle backend-down / slow-AI gracefully — never hang or 500.

Run:  streamlit run frontend/app.py   (BACKEND_URL overridable via env)
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
REQ_TIMEOUT = (5.0, 300.0)  # (connect, read) seconds — 300s read so cold Gemini
# routes (real generation is 17-60s+, up to 180s worst case) finish instead of
# aborting at 10s into "NO DATA / AI ENGINE NOT REACHABLE" and dropping the
# connection mid-request (which kills the dev uvicorn accept loop on Windows).
CACHE_TTL = 60

FALLBACK_CITIES = ["Delhi", "Mumbai", "São Paulo", "Beijing", "Johannesburg"]

# city -> Sensor.Community country code (hyper-local layer)
CITY_COUNTRY = {
    "Delhi": "IN", "Mumbai": "IN", "São Paulo": "BR",
    "Beijing": "CN", "Johannesburg": "ZA",
}

# ---------------------------------------------------------------------------
# Design system — rev 2 (muted dark, professional, no emoji)
# ---------------------------------------------------------------------------
AQI_STYLE = [
    (0, "Good", "#7fae8b"),
    (50, "Moderate", "#c2a45e"),
    (100, "Poor", "#c98d4f"),
    (200, "Very Poor", "#c26a63"),
    (300, "Severe", "#8f4348"),  # aqi >= 300
]

# ---------------------------------------------------------------------------
# Theme presets — muted, cohesive, professional. Keys mirror the CSS variable
# names in APP_CSS (minus the leading --) and are injected as a :root override
# after the base stylesheet, so switching is a pure variable swap.
# ---------------------------------------------------------------------------
THEMES: dict[str, dict[str, str]] = {
    "Midnight Moss": {  # the original — cool near-black + moss
        "bg": "#0a0c10", "bg-panel": "#0f1218", "bg-elevated": "#141822",
        "border": "#1e2430", "border-hover": "#2a313f",
        "text": "#d7dbe2", "text-dim": "#8b91a0", "text-faint": "#5f6672",
        "text-soft": "#a6adba",
        "accent": "#86b88f", "accent-amber": "#c9a86a", "accent-brick": "#c76f64",
    },
    "Graphite Steel": {  # cool blue-grey surfaces + steel blue accent
        "bg": "#0a0d12", "bg-panel": "#10141c", "bg-elevated": "#161c26",
        "border": "#212a38", "border-hover": "#2c3748",
        "text": "#d6dce6", "text-dim": "#8a94a6", "text-faint": "#5e6878",
        "text-soft": "#a5afc0",
        "accent": "#7fa3c9", "accent-amber": "#c7a97a", "accent-brick": "#c47a72",
    },
    "Ember Umber": {  # warm brown-black + bronze
        "bg": "#0e0b09", "bg-panel": "#151110", "bg-elevated": "#1c1714",
        "border": "#2a2320", "border-hover": "#3a312b",
        "text": "#e2dbd3", "text-dim": "#9c918a", "text-faint": "#6b615a",
        "text-soft": "#b4a99f",
        "accent": "#c69a63", "accent-amber": "#d2a75f", "accent-brick": "#c56a5c",
    },
    "Deep Pine": {  # green-black surfaces + brighter moss
        "bg": "#080d0b", "bg-panel": "#0d1412", "bg-elevated": "#121b18",
        "border": "#1d2925", "border-hover": "#283832",
        "text": "#d5e0db", "text-dim": "#869590", "text-faint": "#5b6a65",
        "text-soft": "#a3b2ac",
        "accent": "#6fb389", "accent-amber": "#c3a86a", "accent-brick": "#c2706a",
    },
    "Aubergine": {  # violet-tinted dark + muted mauve
        "bg": "#0b0910", "bg-panel": "#12101a", "bg-elevated": "#181521",
        "border": "#241f30", "border-hover": "#312a41",
        "text": "#ddd8e4", "text-dim": "#928ba4", "text-faint": "#665f76",
        "text-soft": "#aba4bb",
        "accent": "#a58fc6", "accent-amber": "#c7a76f", "accent-brick": "#c4737c",
    },
    "Ink Navy": {  # blue-black + steel blue
        "bg": "#080b12", "bg-panel": "#0d1220", "bg-elevated": "#131a2b",
        "border": "#1d2740", "border-hover": "#283553",
        "text": "#d5dbe8", "text-dim": "#8892aa", "text-faint": "#5a6479",
        "text-soft": "#a3acc0",
        "accent": "#7d9fd0", "accent-amber": "#c8a877", "accent-brick": "#c0726b",
    },
    "Coastal Teal": {  # desaturated teal surfaces + sea-glass accent
        "bg": "#080e0e", "bg-panel": "#0d1515", "bg-elevated": "#121d1d",
        "border": "#1d2b2b", "border-hover": "#283b3b",
        "text": "#d5e2e2", "text-dim": "#869696", "text-faint": "#5b6b6b",
        "text-soft": "#a3b3b3",
        "accent": "#6fb0a8", "accent-amber": "#c3a86a", "accent-brick": "#c2706a",
    },
    "Warm Charcoal": {  # neutral warm grey + clay accent
        "bg": "#0e0d0c", "bg-panel": "#151413", "bg-elevated": "#1c1b19",
        "border": "#2a2825", "border-hover": "#3a3733",
        "text": "#e2ded9", "text-dim": "#9b968f", "text-faint": "#6b6762",
        "text-soft": "#b3aea7",
        "accent": "#c2a084", "accent-amber": "#c9a86a", "accent-brick": "#c2706a",
    },
}
DEFAULT_THEME = "Midnight Moss"

APP_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');

:root {
  --font-ui: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace;

  --bg: #0a0c10;
  --bg-panel: #0f1218;
  --bg-elevated: #141822;
  --border: #1e2430;
  --border-hover: #2a313f;
  --text: #d7dbe2;
  --text-dim: #8b91a0;
  --text-faint: #5f6672;
  --text-soft: #a6adba;
  --accent: #86b88f;
  --accent-amber: #c9a86a;
  --accent-brick: #c76f64;
  --shadow: 0 1px 0 rgba(255,255,255,.02) inset, 0 10px 28px rgba(0,0,0,.38);
}

html { font-size: 106.25%; } /* 16px -> 17px — subtle global scale-up for readability */

html, body, [class*="css"] {
  font-family: var(--font-ui);
  color: var(--text);
  background: var(--bg);
  -webkit-font-smoothing: antialiased;
}

/* strip Streamlit chrome — pure canvas.
   NOTE: keep the toolbar SHELL ([data-testid="stToolbar"]) in the DOM. The
   sidebar reopen arrow (data-testid="stExpandSidebarButton") is rendered as a
   child of it — hiding the whole toolbar traps the user with a collapsed
   sidebar and no way to bring it back. Hide only the menus/actions instead. */
#MainMenu, footer, [data-testid="stDecoration"],
[data-testid="stMainMenu"], [data-testid="stToolbarActions"],
[data-testid="stStatusWidget"],
[data-testid="stAppDeployButton"] { display: none !important; }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbar"] { background: transparent !important; }

/* sidebar reopen control — always visible and on-palette while collapsed */
[data-testid="stExpandSidebarButton"] {
  display: inline-flex !important;
  align-items: center;
  justify-content: center;
  opacity: 1 !important;
  cursor: pointer;
}
[data-testid="stExpandSidebarButton"],
[data-testid="stExpandSidebarButton"] * { color: var(--text-dim) !important; }
[data-testid="stExpandSidebarButton"]:hover,
[data-testid="stExpandSidebarButton"]:hover * { color: var(--accent) !important; }

/* typography — professional scale, tight tracking, no gimmicks */
h1 {
  font-family: var(--font-ui);
  font-weight: 700;
  font-size: 2.0rem !important;
  letter-spacing: -0.02em;
  color: var(--text);
  margin-bottom: .15rem !important;
}
h2 {
  font-family: var(--font-mono);
  font-weight: 500;
  font-size: .78rem !important;
  letter-spacing: .18em;
  text-transform: uppercase;
  color: var(--text-dim);
  border-top: 1px solid var(--border);
  padding-top: .85rem;
  margin-top: 1.9rem !important;
}
h3 {
  font-family: var(--font-mono);
  font-weight: 600;
  font-size: 1.15rem !important;
  letter-spacing: .16em;
  text-transform: uppercase;
  color: var(--text-dim);
  border-bottom: 1px solid var(--border);
  padding: 0 0 .8rem;
  margin: 2.6rem 0 1.3rem !important;
}
[data-testid="stCaptionContainer"] {
  font-family: var(--font-mono);
  font-size: .76rem;
  letter-spacing: .04em;
  color: var(--text-faint) !important;
}

/* sidebar — recessed, data-labelled */
[data-testid="stSidebar"] {
  background: var(--bg);
  border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { font-size: .86rem; }
[data-testid="stSidebar"] hr { border-color: var(--border); }
/* theme the app surface so palette swaps recolour the whole canvas */
[data-testid="stAppViewContainer"], [data-testid="stApp"], [data-testid="stMain"] {
  background: var(--bg);
}

/* selectbox */
[data-baseweb="select"] > div {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
}
[data-baseweb="select"] * {
  font-family: var(--font-mono) !important;
  color: var(--text) !important;
}
/* focus ring + dropdown popover follow the active palette (Streamlit's own
   primaryColor stays moss, so override these explicitly) */
[data-baseweb="select"] > div:focus-within {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 1px var(--accent) !important;
}
[data-baseweb="popover"] [role="listbox"],
[data-baseweb="popover"] ul { background: var(--bg-elevated) !important; }
[data-baseweb="popover"] [role="option"] {
  font-family: var(--font-mono) !important;
  color: var(--text) !important;
  background: transparent !important;
}
[data-baseweb="popover"] [role="option"]:hover,
[data-baseweb="popover"] [role="option"][aria-selected="true"] {
  background: var(--bg-panel) !important;
  color: var(--accent) !important;
}

/* buttons */
.stButton > button, .stButtonBase button {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  color: var(--text-dim) !important;
  font-family: var(--font-mono) !important;
  font-size: .75rem !important;
  letter-spacing: .14em;
  text-transform: uppercase;
  box-shadow: none !important;
  transition: border-color .18s ease, color .18s ease;
}
.stButton > button:hover, .stButtonBase button:hover {
  border-color: var(--accent) !important;
  color: var(--accent) !important;
}

/* metric widget — mono data */
[data-testid="stMetric"] {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
}
[data-testid="stMetricLabel"] {
  font-family: var(--font-mono);
  letter-spacing: .14em;
  font-size: .66rem !important;
  text-transform: uppercase;
  color: var(--text-faint) !important;
}
[data-testid="stMetricValue"] {
  font-family: var(--font-ui) !important;
  font-weight: 700;
  font-size: 2.05rem !important;
  color: var(--text);
}
[data-testid="stMetricDelta"] { font-family: var(--font-mono) !important; font-size: .7rem !important; }

code, pre {
  font-family: var(--font-mono) !important;
  background: var(--bg-panel) !important;
  color: var(--accent) !important;
  font-size: .82em !important;
}

/* ------------------------------------------------------------------ */
/* custom components                                                   */
/* ------------------------------------------------------------------ */
@keyframes riseIn {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: none; }
}
@keyframes pulseDot {
  0%, 100% { opacity: .55; }
  50%      { opacity: 1; }
}

.card {
  background: linear-gradient(180deg, var(--bg-elevated), var(--bg-panel));
  border: 1px solid var(--border);
  border-top: 2px solid var(--cat, var(--border));
  border-radius: 12px;
  padding: 24px 26px 22px;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 9px;
  box-shadow: var(--shadow);
  animation: riseIn .5s cubic-bezier(.2,.7,.3,1) both;
}
.card:nth-child(1) { animation-delay: .02s; }
.card:nth-child(2) { animation-delay: .08s; }
.card:nth-child(3) { animation-delay: .14s; }
.card:nth-child(4) { animation-delay: .20s; }
.card:nth-child(5) { animation-delay: .26s; }
.card:nth-child(6) { animation-delay: .32s; }

.card .eyebrow {
  font-family: var(--font-mono);
  font-size: .68rem;
  letter-spacing: .2em;
  text-transform: uppercase;
  color: var(--text-faint);
}
.card .big {
  font-family: var(--font-ui);
  font-weight: 800;
  font-size: 3.6rem;
  line-height: 1.05;
  letter-spacing: -0.02em;
  color: var(--cat, var(--text));
  margin: 2px 0 4px;
}
.card .med {
  font-family: var(--font-ui);
  font-weight: 700;
  font-size: 1.7rem;
  line-height: 1.15;
  letter-spacing: .01em;
  color: var(--cat, var(--text));
  margin: 4px 0 6px;
  word-break: break-word;
}
.card .meta {
  margin-top: auto;
  padding-top: .8rem;
  border-top: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: .74rem;
  letter-spacing: .04em;
  color: var(--text-faint);
}
.card .sub {
  font-family: var(--font-mono);
  font-weight: 500;
  font-size: .8rem;
  letter-spacing: .03em;
  color: var(--text-soft);
}

.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--dot, var(--text-faint));
  margin-right: 8px;
  vertical-align: 1px;
}
.dot-live { animation: pulseDot 2.4s ease-in-out infinite; }

.notice {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-left: 3px solid var(--cat, var(--accent));
  border-radius: 8px;
  padding: 10px 14px;
  font-family: var(--font-mono);
  font-size: .78rem;
  letter-spacing: .03em;
  color: var(--text-dim);
}

/* inline danger badge — sits beside a section header (e.g. cross-border flag) */
.xb-badge {
  display: inline-block;
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: .6rem;
  letter-spacing: .14em;
  text-transform: uppercase;
  color: var(--accent-brick);
  background: rgba(199, 111, 100, .10);
  border: 1px solid rgba(199, 111, 100, .35);
  border-radius: 4px;
  padding: 2px 9px 3px;
  margin-left: 10px;
  vertical-align: 3px;
  white-space: nowrap;
}

/* multilingual alert rows — one hairline-separated row per language */
.lang-row {
  display: flex;
  gap: 14px;
  padding: 10px 0 11px;
  border-top: 1px solid var(--border);
}
.lang-tag {
  flex: 0 0 92px;
  font-family: var(--font-mono);
  font-size: .62rem;
  letter-spacing: .16em;
  color: var(--text-faint);
  padding-top: 2px;
}
.lang-body {
  flex: 1;
  min-width: 0;
  font-family: var(--font-mono);
  font-size: .72rem;
  line-height: 1.55;
  color: var(--text-soft);
  word-break: break-word;
}

/* the BRICS chart renders as its own compact panel card */
[data-testid="stPlotlyChart"] {
  background: linear-gradient(180deg, var(--bg-elevated), var(--bg-panel));
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 16px;
  max-height: 480px;
  box-sizing: border-box;
}

.card-grid3 {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 26px;
  margin: 16px 0 24px;
}
.row-2col {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 26px;
  margin: 16px 0 24px;
}
.row-2eq {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 26px;
  margin: 16px 0 24px;
}
@media (max-width: 900px) {
  .card-grid3, .row-2col, .row-2eq { grid-template-columns: 1fr; }
}
"""


def risk_from_aqi(aqi: int) -> str:
    for floor, label, _ in AQI_STYLE:
        if aqi <= floor:
            return label
    return "Severe"


def style_for_aqi(aqi: int) -> dict:
    aqi = min(max(aqi, 0), 700)
    for floor, label, hexcolor in AQI_STYLE:
        if aqi <= floor:
            return {"label": label, "hex": hexcolor}
    return {"label": "Severe", "hex": "#8f4348"}


# ---------------------------------------------------------------------------
# HTTP helpers (cached)
# ---------------------------------------------------------------------------
def _get(endpoint: str, params: dict | None = None) -> dict | list | None:
    try:
        resp = requests.get(f"{BACKEND_URL}{endpoint}", params=params, timeout=REQ_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return None


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_cities() -> list[str]:
    data = _get("/api/cities")
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return [c["city"] for c in data]
    return list(FALLBACK_CITIES)


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_aqi_all() -> list[dict]:
    data = _get("/api/aqi")
    return data if isinstance(data, list) else []


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_meta() -> dict:
    data = _get("/api/meta")
    return data if isinstance(data, dict) else {}


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_analysis(city: str) -> dict | None:
    data = _get("/api/analysis", {"city": city})
    return data if isinstance(data, dict) else None


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_forecast(city: str) -> dict | None:
    data = _get("/api/forecast", {"city": city})
    return data if isinstance(data, dict) else None


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_fires(limit: int = 200) -> list[dict]:
    data = _get("/api/fires", {"limit": limit})
    return data if isinstance(data, list) else []


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_crossborder() -> list[dict]:
    data = _get("/api/crossborder")
    return data if isinstance(data, list) else []


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_alerts(city: str) -> dict | None:
    data = _get("/api/alerts", {"city": city})
    return data if isinstance(data, dict) and data else None


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_meteo(city: str) -> dict | None:
    data = _get("/api/meteo", {"city": city})
    return data if isinstance(data, dict) and data else None


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_sensors(country: str) -> list[dict]:
    data = _get("/api/sensors", {"country": country})
    return data if isinstance(data, list) else []


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_status() -> dict:
    data = _get("/api/status")
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# Small render helpers
# ---------------------------------------------------------------------------
def status_dot(color: str, live: bool = False) -> str:
    cls = "dot" + (" dot-live" if live else "")
    return f'<span class="{cls}" style="--dot:{color}"></span>'


def placeholder_card(title: str, desc: str, tag: str, endpoint: str) -> str:
    """A designed, minimal placeholder for future milestones."""
    return (
        f'<div class="card"><div class="eyebrow">{title}</div>'
        f'<div class="sub" style="margin-top:4px;">{desc}</div>'
        f'<div class="meta">SCHEDULED &nbsp;·&nbsp; {tag}</div>'
        f'<div class="meta" style="border-top:none;padding-top:0;">{endpoint}</div></div>'
    )


# ---------------------------------------------------------------------------
# Page shell
# ---------------------------------------------------------------------------
st.set_page_config(page_title="BRICS Climate Intelligence Platform", layout="wide")

# Active palette comes from the sidebar APPEARANCE control (rendered further
# down). Streamlit reruns top-to-bottom on every interaction, so reading the
# session value here is enough for the whole canvas to recolour on the next run.
active_theme = st.session_state.get("theme", DEFAULT_THEME)
if active_theme not in THEMES:
    active_theme = DEFAULT_THEME
_theme_override = ":root {\n" + "\n".join(
    f"  --{key}: {value};" for key, value in THEMES[active_theme].items()
) + "\n}"
st.markdown(f"<style>{APP_CSS}\n{_theme_override}</style>", unsafe_allow_html=True)

st.title("BRICS Climate Intelligence Platform")
st.caption("TRACK 2 · CLEAN AIR & CLIMATE RESILIENCE")

meta = fetch_meta()
backend_ok = "service" in meta
gemini_live = bool(meta.get("gemini_live"))

if backend_ok:
    st.markdown(
        f'<div class="notice">BACKEND CONNECTED &nbsp;·&nbsp; <code>{BACKEND_URL}</code>'
        f"&nbsp;·&nbsp; OWNER: {meta.get('owner', '?')}"
        f"&nbsp;·&nbsp; AI: {'GEMINI LIVE' if gemini_live else 'RULE-BASED FALLBACK'}</div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f'<div class="notice" style="--cat:var(--accent-amber);">'
        f"BACKEND UNREACHABLE AT <code>{BACKEND_URL}</code> — OFFLINE MOCK MODE "
        f"(LAYOUT PREVIEW ONLY)</div>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.markdown("**CITY SELECTOR**")
cities = fetch_cities()
city = st.sidebar.selectbox("City", cities, index=0, label_visibility="collapsed")

readings = fetch_aqi_all()
reading = next((r for r in readings if r["city"] == city), None)

if st.sidebar.button("REFRESH DATA", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("**DATA SOURCES**")

# live/cached/fallback indicators straight from the backend's /api/status
status = fetch_status()
if status.get("sources"):
    _col = {"live": "#86b88f", "cached": "#c9a86a", "fallback": "#8b91a0", "unavailable": "#e24a33"}
    for _s in status["sources"]:
        _stt = _s.get("status", "fallback")
        st.sidebar.markdown(
            f"{status_dot(_col.get(_stt, '#8b91a0'), _stt == 'live')} "
            f"{str(_s.get('layer', _s.get('source', '?'))).upper()} — {_stt.upper()}",
            unsafe_allow_html=True,
        )
    _g = status.get("gemini", {})
    _gstt = _g.get("status", "fallback")
    st.sidebar.markdown(
        f"{status_dot(_col.get(_gstt, '#8b91a0'), _gstt == 'live')} AI REASONING — {_gstt.upper()}",
        unsafe_allow_html=True,
    )
elif reading is not None:
    source = reading.get("source", "unknown")
    live = source not in ("mock", "cached")
    st.sidebar.markdown(
        f"{status_dot('#86b88f' if live else '#c9a86a', live)} AQI READINGS — "
        f"{'LIVE' if live else source.upper()}",
        unsafe_allow_html=True,
    )
    ts = reading.get("timestamp")
    if ts:
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            age_min = int((datetime.now(timezone.utc) - dt).total_seconds() / 60)
            st.sidebar.caption(f"READING AGE: {age_min} MIN")
        except ValueError:
            pass
else:
    st.sidebar.markdown(f"{status_dot('#5f6672')} AQI READINGS — NONE", unsafe_allow_html=True)

# --- appearance — bottom of the city selection window --------------------
st.sidebar.markdown("---")
st.sidebar.markdown("**APPEARANCE**")
st.sidebar.selectbox(
    "Background theme",
    list(THEMES.keys()),
    index=list(THEMES).index(active_theme),
    key="theme",
    label_visibility="collapsed",
)
st.sidebar.caption("BACKGROUND THEME · APPLIES INSTANTLY")

# ---------------------------------------------------------------------------
# Row 1 — three balanced cards: CURRENT AQI / RISK / 24H OUTLOOK
# ---------------------------------------------------------------------------
analysis = fetch_analysis(city)
forecast = fetch_forecast(city)

_badge = (
    '<span class="xb-badge">CROSS-BORDER CONTRIBUTION SUSPECTED</span>'
    if analysis and analysis.get("cross_border_suspected")
    else ""
)
st.markdown(
    f'<h3>CURRENT AIR QUALITY — {city} {_badge}</h3>',
    unsafe_allow_html=True,
)

# --- card 1: current AQI -------------------------------------------------
if reading is not None:
    aqi = reading.get("aqi", 0)
    aqi_st = style_for_aqi(aqi)
    pm25 = reading.get("pm25")
    pm10 = reading.get("pm10")
    parts = []
    if pm25 is not None:
        parts.append(f"PM2.5 {pm25:.0f}")
    if pm10 is not None:
        parts.append(f"PM10 {pm10:.0f}")
    parts.append(reading.get("country", "?"))
    parts.append(f"SRC {reading.get('source', '?')}")
    card_aqi = (
        f'<div class="card" style="--cat:{aqi_st["hex"]};">'
        f'<div class="eyebrow">Current Air Quality Index</div>'
        f'<div class="big">{aqi}</div>'
        f'<div class="sub">{status_dot(aqi_st["hex"])}{aqi_st["label"]} — AQI</div>'
        f'<div class="meta">{"&nbsp;·&nbsp;".join(parts)}</div></div>'
    )
else:
    card_aqi = '<div class="card"><div class="eyebrow">Current Air Quality Index</div><div class="med">NO DATA</div></div>'

# --- card 2: risk assessment --------------------------------------------
if analysis:
    risk = analysis.get("risk_level", "Unknown")
    risk_st = style_for_aqi(reading["aqi"]) if reading else {"hex": "#8b91a0"}
    conf = analysis.get("confidence", 0) * 100
    sources = (analysis.get("likely_sources") or [])[:3]
    src_line = " · ".join(s.upper() for s in sources) if sources else "NO SOURCE DATA"
    card_risk = (
        f'<div class="card" style="--cat:{risk_st["hex"]};">'
        f'<div class="eyebrow">Risk Assessment</div>'
        f'<div class="med" style="font-size:2.15rem;">{risk}</div>'
        f'<div class="sub">AI CONFIDENCE {conf:.0f}%</div>'
        f'<div class="meta">SOURCES: {src_line}</div></div>'
    )
else:
    risk = risk_from_aqi(reading.get("aqi", 0)) if reading else "Unknown"
    card_risk = (
        f'<div class="card"><div class="eyebrow">Risk Assessment</div>'
        f'<div class="med" style="font-size:2.15rem;">{risk}</div>'
        f'<div class="sub">COMPUTED LOCALLY — AI OFFLINE</div></div>'
    )

# --- card 3: 24h outlook -------------------------------------------------
if forecast and reading:
    cur = forecast.get("current_aqi", reading["aqi"])
    f24 = forecast.get("forecast_24h_aqi", cur)
    f6 = forecast.get("forecast_6h_aqi", cur)
    delta = f24 - cur
    arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
    glow_note = ""
    if forecast.get("spike_warning"):
        glow_note = (
            '<div class="notice" style="--cat:var(--accent-amber);margin-top:10px;">'
            f'SPIKE PREDICTED — {str(forecast.get("spike_cause", "")).upper()}</div>'
        )
    card_fc = (
        f'<div class="card" style="--cat:var(--accent);">'
        f'<div class="eyebrow">24h Outlook</div>'
        f'<div class="big" style="font-size:3.2rem;">{f24}</div>'
        f'<div class="sub">{arrow} {delta:+d} VS NOW ({cur}) · 6H {f6}</div>'
        f'<div class="meta">FORECAST CONFIDENCE {forecast.get("forecast_confidence", 0)*100:.0f}%</div>'
        f'{glow_note}</div>'
    )
else:
    card_fc = (
        '<div class="card"><div class="eyebrow">24h Outlook</div>'
        '<div class="med">NO FORECAST</div>'
        '<div class="sub">AI ENGINE NOT REACHABLE</div></div>'
    )

st.markdown(
    f'<div class="card-grid3">{card_aqi}{card_risk}{card_fc}</div>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# ROW 2 — Live Map (folium) + Cross-Border Alerts
# ---------------------------------------------------------------------------
st.subheader("MONITORING BOARD")

fires = fetch_fires(200)
meteo_now = fetch_meteo(city)
events = fetch_crossborder()
center = (reading["lat"], reading["lng"]) if reading else (20.0, 78.0)

with st.container():
    map_col, cb_col = st.columns([3, 2], gap="medium")

    # --- Live Map ----------------------------------------------------------
    with map_col:
        import folium
        from folium.plugins import MarkerCluster

        # Key-free dark tiles (Esri World Dark Gray). CartoDB dark_matter now
        # requires an API key; override via MAP_TILES env var if you have one.
        map_url = os.getenv(
            "MAP_TILES",
            "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/"
            "World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        )
        fmap = folium.Map(
            location=center, zoom_start=4,
            tiles=map_url,
            attr="Esri, HERE, Garmin, © OpenStreetMap contributors, and the GIS User Community",
        )
        # fire hotspots (red, opacity scaled by FRP)
        fg = folium.FeatureGroup(name=f"Fire hotspots ({len(fires)})")
        for f in fires:
            try:
                frp = float(f.get("frp") or 0)
                lat, lng = float(f["lat"]), float(f["lng"])
            except (KeyError, TypeError, ValueError):
                continue
            intensity = min(0.9, 0.25 + frp / 120.0)
            fg.add_child(folium.CircleMarker(
                (lat, lng), radius=3 + min(6, frp / 12), color="#ff6b4a",
                fill=True, fill_color="#e24a33", fill_opacity=intensity, opacity=0.9))
        fmap.add_child(fg)
        # BRICS city markers colored by AQI
        for r in readings:
            try:
                lat, lng, val = float(r["lat"]), float(r["lng"]), int(r.get("aqi") or 0)
            except (KeyError, TypeError, ValueError):
                continue
            hexc = style_for_aqi(val)["hex"]
            selected = r.get("city") == city
            fmap.add_child(folium.CircleMarker(
                (lat, lng), radius=11 if selected else 7, color=hexc,
                fill=True, fill_color=hexc, fill_opacity=0.95, opacity=1.0,
                tooltip=f"{r.get('city')} — AQI {val} ({style_for_aqi(val)['label']})"))
        # wind vector at selected city (meteo direction is FROM; draw transport TO)
        if meteo_now:
            try:
                to_deg = (float(meteo_now.get("wind_direction_deg", 0)) + 180.0) % 360.0
                rad = math.radians(to_deg)
                dlat = math.cos(rad) * 1.6
                dlng = math.sin(rad) * 1.6 / max(0.3, math.cos(math.radians(center[0])))
                fmap.add_child(folium.PolyLine(
                    [center, (center[0] + dlat, center[1] + dlng)],
                    color="#7fd1ff", weight=3, opacity=0.9,
                    tooltip=f"Wind {meteo_now.get('wind_speed_kmh')} km/h from "
                            f"{meteo_now.get('wind_direction_label')}"))
            except (KeyError, TypeError, ValueError):
                pass
        # hyper-local citizen sensors (small grey dots)
        cc = CITY_COUNTRY.get(city, "IN")
        sensors = fetch_sensors(cc)
        if sensors:
            sg = folium.FeatureGroup(name=f"Citizen sensors ({len(sensors)})")
            for s in sensors[:120]:
                try:
                    sg.add_child(folium.CircleMarker(
                        (float(s["lat"]), float(s["lng"])), radius=2.5, color="#9aa0aa",
                        fill=True, fill_color="#c9ccd4", fill_opacity=0.75, opacity=0.6))
                except (KeyError, TypeError, ValueError):
                    continue
            fmap.add_child(sg)
        fmap.add_child(folium.LayerControl(collapsed=True, position="topright"))
        # folium >=0.17: full HTML doc via root.render(); older: get_root_html()
        if hasattr(fmap, "get_root"):
            _map_html = fmap.get_root().render()
        else:  # pragma: no cover
            _map_html = fmap.get_root_html()
        st.components.v1.html(_map_html, height=470, scrolling=False)

    # --- Cross-Border Alerts ----------------------------------------------
    with cb_col:
        if events:
            for e in events[:3]:
                ev_color = "#e24a33" if str(e.get("severity", "")).lower() in ("high", "severe", "critical") else "#c9a86a"
                st.markdown(
                    f'<div class="card" style="--cat:{ev_color};margin-bottom:10px;">'
                    f'<div class="eyebrow">Transboundary Event · {str(e.get("severity", "?")).upper()}</div>'
                    f'<div class="med" style="font-size:1.15rem;">'
                    f'{e.get("source_city", "?")} → {e.get("affected_city", "?")}</div>'
                    f'<div class="sub">{e.get("source_cause", "?").upper()} · '
                    f'{e.get("source_country", "?")} → {e.get("affected_country", "?")} · '
                    f'{e.get("transport_direction", "?")} · {e.get("distance_km", "?")} KM</div>'
                    f'<div class="meta">{str(e.get("evidence_summary", ""))[:220]}</div></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div class="card"><div class="eyebrow">Cross-Border Alerts</div>'
                '<div class="sub">No active transboundary event detected '
                '(winds do not support regional transport).</div></div>',
                unsafe_allow_html=True,
            )

# --- BRICS Comparison chart (plotly, WHO guideline line) — full width -------
import plotly.graph_objects as go

names = [r.get("city", "?") for r in readings]
pm25_vals = [float(r.get("pm25") or 0) for r in readings]
bar_colors = [style_for_aqi(int(r.get("aqi") or 0))["hex"] for r in readings]
th = THEMES[active_theme]
fig = go.Figure()
fig.add_trace(go.Bar(
    x=names, y=pm25_vals,
    marker=dict(color=bar_colors, cornerradius=6, line=dict(width=0)),
    text=[f"{v:.0f}" for v in pm25_vals], textposition="outside",
    textfont=dict(family="JetBrains Mono, monospace", size=10, color=th["text-soft"]),
    hovertemplate="%{x}<br>PM2.5 %{y:.1f} µg/m³<extra></extra>"))
fig.add_hline(
    y=15, line_color="#e24a33", line_dash="dash", line_width=1.4,
    annotation_text="WHO 24h · 15", annotation_position="top right",
    annotation_font=dict(family="JetBrains Mono, monospace", size=9, color="#e24a33"),
)
fig.update_layout(
    title=dict(
        text="PM2.5 (µg/m³) vs WHO 24H GUIDELINE · BRICS CITIES",
        font=dict(family="JetBrains Mono, monospace", size=10.5, color=th["text-soft"]),
        x=0.02, xanchor="left",
    ),
    margin=dict(l=2, r=12, t=46, b=8), height=420, showlegend=False,
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="JetBrains Mono, monospace", size=10.5, color=th["text-dim"]),
    bargap=0.5,
    xaxis=dict(color=th["text-faint"]),
    yaxis=dict(gridcolor=th["border"], zeroline=False, tickcolor=th["border"]),
    hoverlabel=dict(bgcolor=th["bg-elevated"], bordercolor=th["border"],
                    font=dict(family="JetBrains Mono, monospace", size=10, color=th["text"])),
)
try:
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
except TypeError:  # older streamlit
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# --- Multilingual alerts (Hindi / Portuguese / English) — full width --------
alert = fetch_alerts(city)
if alert:
    urg = str(alert.get("urgency", "watch")).lower()
    urg_color = {"immediate": "#e24a33", "advisory": "#c9a86a"}.get(urg, "#86b88f")
    _langs = (
        ("HINDI", alert.get("message_hindi", "—")),
        ("PORTUGUESE", alert.get("message_portuguese", "—")),
        ("ENGLISH", alert.get("message_english", "—")),
    )
    _rows = "".join(
        f'<div class="lang-row"><div class="lang-tag">{tag}</div>'
        f'<div class="lang-body">{text}</div></div>'
        for tag, text in _langs
    )
    st.markdown(
        f'<div class="card" style="--cat:{urg_color};margin-bottom:22px;">'
        f'<div class="eyebrow">Authority Alert · {urg.upper()}</div>'
        f'<div class="med" style="font-size:1.2rem;">{alert.get("city", city)} — '
        f'{alert.get("risk_level", "?")}</div>'
        f'{_rows}'
        f'<div class="meta">TARGET: {alert.get("target_authority", "—")}</div></div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        '<div class="card"><div class="eyebrow">Multilingual Alerts</div>'
        '<div class="sub">Alert service unavailable — backend offline.</div></div>',
        unsafe_allow_html=True,
    )

# --- Citizen Photo Intake + Hyper-Local Sensors -----------------------------
photo_col, sensor_col = st.columns([1, 1], gap="medium")

with photo_col:
    upload = st.file_uploader("Upload pollution photo (jpg/png)", type=["jpg", "jpeg", "png"])
    if upload is not None:
        try:
            resp = requests.post(
                f"{BACKEND_URL}/api/analyze-photo",
                data={"city": city},
                files={"file": (upload.name, upload.getvalue(), upload.type or "image/jpeg")},
                timeout=(5, 90),
            )
            resp.raise_for_status()
            pr = resp.json()
            sev = int(pr.get("severity_score") or 0)
            st.markdown(
                f'<div class="card" style="--cat:{"#e24a33" if sev >= 6 else "#c9a86a"};">'
                f'<div class="eyebrow">Gemini Vision Result</div>'
                f'<div class="med" style="font-size:1.15rem;">{pr.get("pollution_type", "—")}</div>'
                f'<div class="sub">AQI CATEGORY: {pr.get("estimated_aqi_category", "—")} · '
                f'VISIBILITY: {pr.get("visibility_km", "—")} KM · SEVERITY: {sev}/10</div>'
                f'<div class="meta">SOURCE: {pr.get("likely_source", "—")}<br>'
                f'ADVICE: {pr.get("recommendation", "—")} '
                f'(confidence {float(pr.get("confidence", 0))*100:.0f}%)</div></div>',
                unsafe_allow_html=True,
            )
        except requests.RequestException as e:
            st.markdown(
                f'<div class="notice" style="--cat:#e24a33;">PHOTO ANALYSIS FAILED: {e.__class__.__name__}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div class="card"><div class="eyebrow">Citizen Photo Intake</div>'
            '<div class="sub">Upload a smog/haze photo — Gemini Vision estimates pollution '
            'type, visibility, severity (1–10) and health advice.</div></div>',
            unsafe_allow_html=True,
        )

with sensor_col:
    sensors = fetch_sensors(CITY_COUNTRY.get(city, "IN"))
    if sensors:
        top = sorted(sensors, key=lambda s: float(s.get("pm25") or 0), reverse=True)[:8]
        worst = float(top[0].get("pm25") or 0)
        rows_html = "".join(
            f'<tr><td style="padding:2px 6px 2px 0;color:{th["text-faint"]};">'
            f'{float(s.get("pm25") or 0):.0f} µg/m³</td>'
            f'<td style="padding:2px 0;color:{th["text-soft"]};">{s.get("city", "")} '
            f'· {float(s.get("lat") or 0):.2f}, {float(s.get("lng") or 0):.2f}</td></tr>'
            for s in top
        )
        st.markdown(
            f'<div class="card"><div class="eyebrow">Hyper-Local Citizen Sensors</div>'
            f'<div class="med" style="font-size:1.6rem;">{len(sensors)} readings · peak {worst:.0f} µg/m³</div>'
            f'<table style="width:100%;border-collapse:collapse;font-family:var(--font-mono);font-size:.72rem;">'
            f'{rows_html}</table>'
            f'<div class="meta">SENSOR.COMMUNITY · COUNTRY {CITY_COUNTRY.get(city, "IN")} · '
            f'GRANULARITY BELOW GOVERNMENT STATIONS</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="card"><div class="eyebrow">Hyper-Local Citizen Sensors</div>'
            '<div class="sub">No citizen sensor readings for this country right now.</div></div>',
            unsafe_allow_html=True,
        )

st.divider()
st.caption(
    f"DESIGN BY SARTHAK & ANOUSHKA · DATA PIPELINE BY SUJAL · "
    f"BACKEND {BACKEND_URL} · REFRESH {datetime.now().strftime('%H:%M:%S')} UTC"
)