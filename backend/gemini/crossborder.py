"""Sarthak — Module 3: Cross-border pollution transport detection.

Input:  list[AQIReading] + list[FireHotspot] + list[MeteoData] (all cities)
Output: list[GeminiCrossBorderEvent]

Gemini looks at wind vectors, fire locations and multiple city AQI readings
SIMULTANEOUSLY and identifies active transboundary transport events, e.g.:
  - Punjab crop burning + NW wind -> Delhi / Lahore AQI spike
  - Amazon wildfires -> São Paulo smoke
  - Mpumalanga highveld -> Johannesburg

Contract with Sujal's backend (backend/main.py):
    result = gem_cross.detect_crossborder(readings, fires, meteos)
Raises on failure -> main.py falls back to rule_crossborder(). Never 500.
"""
from __future__ import annotations

import os

from backend.gemini._common import gemini_retry, get_client, to_model
from backend.models import (
    AQIReading,
    FireHotspot,
    GeminiCrossBorderEvent,
    MeteoData,
)

# NOTE: Pro-class models (gemini-3.1-pro*) have ZERO free-tier quota on
# API-key accounts ("limit: 0"). flash is free-tier capable and handles the
# reasoning here fine. Swap to a Pro model only if the team pays for quota.
MODEL = os.getenv("GEMINI_CROSS_MODEL", "gemini-3.6-flash")

# Known high-value corridors the challenge wants surfaced.
SYSTEM_PROMPT = (
    "You are a transboundary air-quality analyst for the BRICS Climate "
    "Intelligence Platform. You detect when pollution from one region/country "
    "is transported across a border and affects another city.\n"
    "Always reason about wind vectors: a city downwind of an intense fire "
    "cluster is the affected city; the fire region is the source.\n"
    "Known corridors you must pay attention to:\n"
    "  1. Indo-Gangetic Plain: crop-residue burning in Punjab/Haryana "
    "(India) transported toward Delhi (India) and Lahore (Pakistan).\n"
    "  2. Amazon basin fires transported toward São Paulo (Brazil).\n"
    "  3. Mpumalanga highveld industrial/wildfire emissions toward "
    "Johannesburg (South Africa).\n"
    "Return a list of active events (empty list if none are supported by the "
    "wind + fire + AQI evidence). Only report events with real supporting "
    "evidence. transport_direction uses compass labels (e.g. 'NW to SE'). "
    "severity: 'low'|'moderate'|'high'|'critical'."
)


def _compact_context(
    readings: list[AQIReading], meteos: list[MeteoData], fires: list[FireHotspot]
) -> str:
    """Serialize inputs into a compact, Gemini-friendly summary."""
    lines: list[str] = ["## City AQI + meteorology (all monitored cities)"]
    for r in readings:
        m = next((x for x in meteos if x.city.lower() == r.city.lower()), None)
        if m:
            lines.append(
                f"- {r.city}, {r.country}: AQI {r.aqi} (PM2.5 {r.pm25}) | wind "
                f"{m.wind_speed_kmh} km/h from {m.wind_direction_label} "
                f"({round(m.wind_direction_deg)}°) | {m.temperature_c}°C"
            )
        else:
            lines.append(f"- {r.city}, {r.country}: AQI {r.aqi} (PM2.5 {r.pm25}) | wind n/a")

    # Fire clusters by coarse region (lat/lng buckets) — keeps payload small.
    import math

    buckets: dict[tuple[int, int], list[FireHotspot]] = {}
    for f in fires:
        key = (math.floor(f.lat / 5) * 5, math.floor(f.lng / 5) * 5)
        buckets.setdefault(key, []).append(f)

    lines.append("\n## Fire clusters (5°x5° grid) — count, max FRP MW, centroid")
    for (blat, blng), fs in sorted(buckets.items(), key=lambda kv: -len(kv[1]))[:12]:
        max_frp = max(x.frp for x in fs)
        clat = round(sum(x.lat for x in fs) / len(fs), 2)
        clng = round(sum(x.lng for x in fs) / len(fs), 2)
        lines.append(
            f"- {len(fs)} hotspots around ({clat}, {clng}) | max FRP {round(max_frp, 1)} MW"
        )
    return "\n".join(lines)


@gemini_retry
def _call_gemini(
    readings: list[AQIReading],
    fires: list[FireHotspot],
    meteos: list[MeteoData],
) -> list[GeminiCrossBorderEvent]:
    client = get_client()
    prompt = _compact_context(readings, meteos, fires)
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt + (
            "\n\nIdentify any ACTIVE transboundary pollution transport events "
            "visible in this data. For each, give source country/city, cause, "
            "affected city/country, compass transport direction, distance in km, "
            "severity, and a short evidence summary quoting the actual numbers. "
            "Return structured JSON as a LIST (may be empty)."
        ),
        config={
            "system_instruction": SYSTEM_PROMPT,
            "response_mime_type": "application/json",
            "response_schema": list[GeminiCrossBorderEvent],
            "temperature": 0.2,
        },
    )
    return to_model(response, list[GeminiCrossBorderEvent])


def detect_crossborder(
    readings: list[AQIReading], fires: list[FireHotspot], meteos: list[MeteoData]
) -> list[GeminiCrossBorderEvent]:
    """Gemini transboundary event detection (Sujal's contract). Raises on failure."""
    events = _call_gemini(readings, fires, meteos)
    # De-duplicate + keep only events whose affected city we actually monitor.
    known = {r.city.lower() for r in readings}
    seen: set[tuple] = set()
    out: list[GeminiCrossBorderEvent] = []
    for e in events:
        key = (e.source_country, e.source_city, e.affected_city)
        if key in seen:
            continue
        if e.affected_city.lower() not in known:
            continue
        seen.add(key)
        e.distance_km = round(min(max(e.distance_km, 0.0), 20000.0), 1)
        out.append(e)
    return out