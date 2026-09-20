"""Sarthak — Module 1: AQI Analysis (core module).

Input:  AQIReading + MeteoData for the same city
Output: GeminiAQIAnalysis

Gemini reasons over raw sensor numbers + wind data to answer:
  - What is causing this AQI level?
  - How much is coming from cross-border sources?
  - What health risk does it represent?

Contract with Sujal's backend (backend/main.py):
    result = gem_aqi.analyze_aqi(reading, meteo)   # raises -> rule fallback
Any exception (missing key, API error, schema mismatch) is intentional:
main.py catches it and serves rule_analysis() instead. Never 500.
"""
from __future__ import annotations

import math
import os
from typing import Optional

from backend.gemini._common import gemini_retry, get_client, to_model
from backend.models import AQIReading, GeminiAQIAnalysis, MeteoData

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# Domain facts the challenge wants the AI to reason with.
SYSTEM_PROMPT = (
    "You are a senior air quality scientist analyzing BRICS city data. "
    "Known context you must apply: "
    "(1) ~85% of urban PM2.5 in India is transboundary — it originates in "
    "other regions/countries and is transported by wind. "
    "(2) Amazon fires transport smoke 2,000+ km to São Paulo. "
    "(3) The Indo-Gangetic Plain experiences seasonal crop-residue burning "
    "that drives cross-border pollution events toward Pakistan. "
    "Reason from the measurements and meteorology, be conservative with "
    "'cross_border_suspected' (only true when wind/evidence supports "
    "transport), and return structured JSON matching the schema.\n\n"
    "VOCABULARY (use EXACTLY these values, never synonyms):\n"
    "- risk_level: one of 'Good' (AQI<=50), 'Moderate' (51-100), "
    "'Poor' (101-200), 'Very Poor' (201-300), 'Severe' (>300).\n"
    "- primary_pollutant: 'PM2.5', 'PM10', 'NO2', 'SO2', 'O3' or 'CO'.\n"
    "- likely_sources entries: use short labels like 'crop residue burning', "
    "'industrial emissions', 'vehicular traffic', 'construction dust', "
    "'wildfire smoke', 'stagnant meteorology', 'local sources'.\n"
    "- cross_border_contribution_pct: 0-100 float.\n"
    "- confidence: 0-1 float."
)

USER_PROMPT = """Air quality reading:
- City: {city}, {country}
- Current AQI (EPA scale): {aqi}
- PM2.5: {pm25} µg/m³ (WHO 24h guideline: 15 µg/m³)
- PM10: {pm10} µg/m³
- NO2: {no2} | SO2: {so2}

Meteorology right now:
- Wind: {wind_speed} km/h from {wind_label} ({wind_deg}°)
- Temperature: {temp}°C, Humidity: {humidity}%

Analyze the likely pollution sources and estimate the cross-border
contribution percentage (0-100). Summarize the health advisory for the
general public. Return structured JSON only."""


@gemini_retry
def _call_gemini(reading: AQIReading, meteo: MeteoData) -> GeminiAQIAnalysis:
    """Single (retried) Gemini call. Raised errors bubble to analyze_aqi."""
    client = get_client()
    user = USER_PROMPT.format(
        city=reading.city,
        country=reading.country,
        aqi=reading.aqi,
        pm25=reading.pm25,
        pm10=reading.pm10,
        no2=reading.no2 if reading.no2 is not None else "n/a",
        so2=reading.so2 if reading.so2 is not None else "n/a",
        wind_speed=meteo.wind_speed_kmh,
        wind_label=meteo.wind_direction_label,
        wind_deg=round(meteo.wind_direction_deg),
        temp=meteo.temperature_c,
        humidity=meteo.humidity_pct,
    )
    response = client.models.generate_content(
        model=MODEL,
        contents=user,
        config={
            "system_instruction": SYSTEM_PROMPT,
            "response_mime_type": "application/json",
            "response_schema": GeminiAQIAnalysis.model_json_schema(),
            "temperature": 0.2,
        },
    )
    return to_model(response, GeminiAQIAnalysis)


def fallback_analysis(reading: AQIReading, meteo: MeteoData) -> GeminiAQIAnalysis:
    """Deterministic stand-in for direct calls / testing without a key.

    Mirrors backend/main.rule_analysis intent so behavior stays sane when
    the key is absent — Sujal's endpoint still prefers his own rule_analysis.
    """
    risk = (
        "Good" if reading.aqi <= 50
        else "Moderate" if reading.aqi <= 100
        else "Poor" if reading.aqi <= 200
        else "Very Poor" if reading.aqi <= 300
        else "Severe"
    )
    sources: list[str] = []
    if reading.pm25 > 55:
        sources.append("agricultural burning / regional biomass")
    if reading.pm25 > 35:
        sources.append("industrial emissions")
    if meteo.wind_speed_kmh < 10:
        sources.append("stagnant meteorology (low dispersion)")
    if not sources:
        sources = ["traffic", "local sources"]
    return GeminiAQIAnalysis(
        city=reading.city,
        risk_level=risk,
        primary_pollutant="PM2.5" if reading.pm25 / max(reading.pm10, 1) > 0.4 else "PM10",
        health_advisory="Limit outdoor exertion based on current risk level.",
        likely_sources=sources,
        cross_border_suspected=False,
        cross_border_contribution_pct=round(min(20.0, reading.aqi * 0.1), 1),
        confidence=0.5,
    )


def analyze_aqi(reading: AQIReading, meteo: MeteoData) -> GeminiAQIAnalysis:
    """Gemini analysis of one city's AQI + meteorology (Sujal's contract).

    Raises on any failure (missing key, API error, schema mismatch).
    Sujal's backend/main.py catches and serves rule_analysis() as the
    fallback — never mask errors inside the module.
    """
    result = _call_gemini(reading, meteo)
    # Ground-truth fields always come from our inputs, never from the LLM.
    result.city = reading.city
    result.cross_border_contribution_pct = round(
        min(max(result.cross_border_contribution_pct, 0.0), 100.0), 1
    )
    result.confidence = round(min(max(result.confidence, 0.0), 1.0), 2)
    return result


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km — reused by forecast/crossborder later."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# Also expose distance helper for sibling modules without circular imports.
distance_km = _haversine_km


if __name__ == "__main__":
    # Quick self-test: python -m backend.gemini.aqi_analysis
    # Uses Sujal's resilience pattern: live -> cache -> fallback (no keys needed).
    import asyncio

    from backend.pipeline import meteo as meteo_mod
    from backend.pipeline import openaq as openaq_mod

    async def _demo() -> None:
        try:
            rows = await openaq_mod.fetch_aqi_all()
        except Exception:
            rows = openaq_mod.load_cache() or openaq_mod.fallback()
        reading = rows[0]
        try:
            meteos = await meteo_mod.fetch_meteo_all()
        except Exception:
            meteos = meteo_mod.fallback()
        meteo_row = next((m for m in meteos if m.city == reading.city), None)
        if meteo_row is None:
            meteo_row = meteo_mod.fallback_city(reading.city)
        result = analyze_aqi(reading, meteo_row)
        print(result.model_dump_json(indent=2))

    asyncio.run(_demo())