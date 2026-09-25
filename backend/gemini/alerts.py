"""Sarthak — Module 4: Multilingual authority alerts.

Input:  GeminiAQIAnalysis + optional GeminiCrossBorderEvent
Output: AlertMessage (Hindi + Portuguese + English in ONE Gemini call)

Contract with Sujal's backend (backend/main.py):
    result = gem_alerts.generate_alert(analysis, event)
    result = gem_photo.analyze_photo(photo)
Raises on failure -> main.py falls back to rule_alert(). Never 500.
"""
from __future__ import annotations

import os

from backend.gemini._common import gemini_retry, get_client, to_model
from backend.models import (
    AlertMessage,
    GeminiAQIAnalysis,
    GeminiCrossBorderEvent,
)

MODEL = os.getenv("GEMINI_ALERT_MODEL", "gemini-3.6-flash")

# Known target authorities — ground truth from the team, not the LLM.
AUTHORITIES = {
    "Delhi": "Delhi Pollution Control Committee",
    "Mumbai": "Maharashtra Pollution Control Board",
    "São Paulo": "CETESB São Paulo",
    "Beijing": "Beijing Municipal Ecology and Environment Bureau",
    "Johannesburg": "City of Johannesburg Air Quality Unit",
}

SYSTEM_PROMPT = (
    "You are the official alert system of the BRICS Climate Intelligence "
    "Platform. You write precise, actionable public-health alerts for "
    "citizens and authorities. Messages must be factual (no invented numbers "
    "beyond what is provided), calm but serious, and suitable for SMS and "
    "public broadcast. urgency: 'immediate' for Very Poor/Severe, 'advisory' "
    "for Poor, 'watch' for Good/Moderate. Return structured JSON exactly "
    "matching the schema — the three message_* fields must be the SAME alert "
    "in each language. The message_hindi field must be written ENTIRELY in the "
    "Devanagari script (हिन्दी लिपि) — no Latin/English words or sentences; "
    "only unavoidable units such as PM2.5, N95 and AQI may remain in Latin."
)


@gemini_retry
def _call_gemini(
    analysis: GeminiAQIAnalysis, crossborder: GeminiCrossBorderEvent | None
) -> AlertMessage:
    client = get_client()
    cross_txt = (
        f"Cross-border source: {crossborder.source_cause} in "
        f"{crossborder.source_city}, {crossborder.source_country} — "
        f"transporting toward {crossborder.affected_city} "
        f"({crossborder.transport_direction}, {crossborder.distance_km} km)."
        if crossborder
        else "No active cross-border source; pollution is local in origin."
    )
    prompt = f"""Generate an official air quality alert for {analysis.city}.

Current situation: {analysis.risk_level} risk — primary pollutant: {analysis.primary_pollutant}.
Health advisory: {analysis.health_advisory}
Likely sources: {', '.join(analysis.likely_sources)}
Cross-border information: {cross_txt}

Write the alert message in THREE languages (same meaning, natural in each):
1. Hindi — for Indian authorities and citizens (must be full Devanagari script)
2. Portuguese — for Brazilian authorities and citizens
3. English — for international coordination

Also select the target authority to alert immediately and the urgency level
('immediate' | 'advisory' | 'watch'). Return structured JSON only."""
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={
            "system_instruction": SYSTEM_PROMPT,
            "response_mime_type": "application/json",
            "response_schema": AlertMessage.model_json_schema(),
            "temperature": 0.3,
        },
    )
    return to_model(response, AlertMessage)


def generate_alert(
    analysis: GeminiAQIAnalysis, crossborder: GeminiCrossBorderEvent | None
) -> AlertMessage:
    """Gemini multilingual alert (Sujal's contract). Raises on failure."""
    result = _call_gemini(analysis, crossborder)
    # Ground truth from the team's mapping, not the LLM.
    result.city = analysis.city
    result.risk_level = analysis.risk_level
    if analysis.city in AUTHORITIES:
        result.target_authority = AUTHORITIES[analysis.city]
    return result