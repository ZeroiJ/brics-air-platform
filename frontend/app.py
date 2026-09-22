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

import os
from datetime import datetime, timezone

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
REQ_TIMEOUT = (3.0, 10.0)  # (connect, read) seconds
CACHE_TTL = 60

FALLBACK_CITIES = ["Delhi", "Mumbai", "São Paulo", "Beijing", "Johannesburg"]

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
  padding: 20px 22px 18px;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
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

.card-grid3 {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin: 6px 0 8px;
}
.row-2col {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 14px;
  margin: 6px 0 8px;
}
.row-2eq {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin: 6px 0 8px;
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
if reading is not None:
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
st.subheader(f"CURRENT AIR QUALITY — {city}")

analysis = fetch_analysis(city)
forecast = fetch_forecast(city)

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
    if analysis.get("cross_border_suspected"):
        card_risk += (
            '<div class="notice" style="--cat:var(--accent-brick);margin-top:10px;">'
            'CROSS-BORDER CONTRIBUTION SUSPECTED</div>'
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
# Rows 2-3 + below the fold — designed minimal placeholders (future milestones)
# ---------------------------------------------------------------------------
st.subheader("MONITORING BOARD")

st.markdown(
    '<div class="row-2col">'
    + placeholder_card(
        "Live Map",
        "Fire hotspots + AQI city markers + wind vectors. ",
        "22 SEP",
        "ENDPOINT /api/fires",
    )
    + placeholder_card(
        "Cross-Border Alerts",
        "Active transboundary transport events.",
        "22–23 SEP",
        "ENDPOINT /api/crossborder",
    )
    + "</div>",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="row-2eq">'
    + placeholder_card(
        "BRICS Comparison",
        "PM2.5 bar chart vs WHO 24h guideline (15 µg/m³).",
        "23 SEP",
        "ENDPOINT /api/aqi",
    )
    + placeholder_card(
        "Multilingual Alerts",
        "HINDI · PORTUGUESE · ENGLISH — one alert, three languages.",
        "23 SEP",
        "ENDPOINT /api/alerts",
    )
    + "</div>",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="row-2eq">'
    + placeholder_card(
        "Citizen Photo Intake",
        "Upload a photo; Gemini Vision grades the pollution.",
        "24 SEP",
        "ENDPOINT /api/analyze-photo",
    )
    + placeholder_card(
        "Hyper-Local Sensors",
        "Sensor.Community readings as fine-grained dots.",
        "24 SEP",
        "ENDPOINT /api/sensors",
    )
    + "</div>",
    unsafe_allow_html=True,
)

st.divider()
st.caption(
    f"REFERENCE BUILD BY SARTHAK FOR ANOUSHKA · 21 SEP 2026 · "
    f"BACKEND {BACKEND_URL} · REFRESH {datetime.now().strftime('%H:%M:%S')} UTC"
)