"""Federation registry — BRICS model exchange.

PS requirement: *"designed for interoperability so BRICS nations can share
predictive models and coordinate resources."*

What this file is
-----------------
A **contract registry**, not a model zoo. Each card describes the wire format
of a reasoning module that is *already deployed on this node*, so another
BRICS node could call the same interface without reverse-engineering it.

What this file is deliberately NOT
----------------------------------
A set of trained weights. `work-division.md` lists "train custom ML models" as
an anti-pattern, and this project follows it. Every card therefore carries
`trained=False` and points at the real in-repo module via `module`. Nothing
here is invented: the input/output schemas are the actual Pydantic models in
`backend/models.py`, the corridors are the ones the cross-border detector
actually evaluates, and the countries are the five BRICS cities in
`BRICS_CITIES`.

This is the honest version of "share predictive models": we publish the
interoperable interface and prove it already runs across five countries,
rather than dressing up a stub as a trained artifact.
"""
from __future__ import annotations

from backend.models import FederationRegistry, ModelCard

NODE = "brics-air-node/india-1"

_NOTE = (
    "Declared interoperability contracts for the reasoning modules deployed on "
    "this node. No models are trained in this project (see work-division.md "
    "anti-patterns), so every card carries trained=false and names the real "
    "in-repo module that implements it. These are the wire formats a BRICS node "
    "would exchange to share predictive capability across the network."
)

REGISTRY = FederationRegistry(
    protocol="BRICS-AIR-MODEL-EXCHANGE/1.0",
    node=NODE,
    note=_NOTE,
    models=[
        ModelCard(
            id="brics-aqi-interpretation-v1",
            name="AQI Cause Attribution",
            version="1.0.0",
            module="backend/gemini/aqi_analysis.py",
            kind="gemini_reasoning",
            trained=False,
            task="aqi_cause_attribution",
            input_layers=["L1 government AQI (OpenAQ / WAQI)", "L3 meteorology (Open-Meteo)"],
            input_schema={
                "AQIReading.aqi": "int",
                "AQIReading.pm25": "float",
                "AQIReading.pm10": "float",
                "AQIReading.source": "str",
                "MeteoData.wind_direction_label": "str",
                "MeteoData.wind_speed_kmh": "float",
                "MeteoData.humidity_pct": "float",
            },
            output_schema="GeminiAQIAnalysis",
            corridors=["Indo-Gangetic Plain (IN)", "Beijing-Tianjin (CN)"],
            countries=["IN", "CN", "BR", "ZA"],
        ),
        ModelCard(
            id="brics-smoke-transport-xborder-v1",
            name="Transboundary Smoke Transport Detection",
            version="1.0.0",
            module="backend/gemini/crossborder.py",
            kind="gemini_reasoning",
            trained=False,
            task="transboundary_pollution_transport",
            input_layers=[
                "L1 government AQI (OpenAQ / WAQI)",
                "L2 satellite fire hotspots (NASA FIRMS VIIRS)",
                "L3 meteorology (Open-Meteo)",
            ],
            input_schema={
                "list[AQIReading]": "5 BRICS cities",
                "list[FireHotspot]": "lat/lng/brightness/frp/satellite",
                "list[MeteoData]": "wind vector per city",
            },
            output_schema="GeminiCrossBorderEvent",
            corridors=["Indo-Gangetic Plain (IN->PK)", "Amazon Basin (BR)"],
            countries=["IN", "PK", "BR"],
        ),
        ModelCard(
            id="brics-aqi-forecast-6h24h-v1",
            name="6h / 24h AQI Spike Forecast",
            version="1.0.0",
            module="backend/gemini/forecast.py (rule_forecast fallback in backend/main.py)",
            kind="rule_based_heuristic",
            trained=False,
            task="aqi_spike_forecast",
            input_layers=[
                "L1 government AQI (OpenAQ / WAQI)",
                "L2 satellite fire hotspots (NASA FIRMS VIIRS)",
                "L3 meteorology (Open-Meteo)",
            ],
            input_schema={
                "AQIReading.aqi": "int",
                "MeteoData.wind_speed_kmh": "float",
                "FireHotspot.frp": "float (MW)",
                "FireHotspot.lat/lng": "float (nearby-fire radius: 500 km)",
            },
            output_schema="GeminiForecast",
            corridors=["Indo-Gangetic Plain (IN->PK)", "Amazon Basin (BR)", "Beijing-Tianjin (CN)"],
            countries=["IN", "PK", "BR", "CN", "ZA"],
        ),
        ModelCard(
            id="brics-citizen-photo-vision-v1",
            name="Citizen Photo Pollution Attribution",
            version="1.0.0",
            module="backend/gemini/photo_analysis.py",
            kind="gemini_reasoning",
            trained=False,
            task="citizen_photo_pollution_attribution",
            input_layers=["L4 citizen photo upload (base64 image)"],
            input_schema={
                "CitizenPhoto.city": "str",
                "CitizenPhoto.image_base64": "str (JPEG / PNG)",
            },
            output_schema="GeminiPhotoResult",
            corridors=["Any — citizen-submitted, city-scoped"],
            countries=["IN", "BR", "CN", "ZA"],
        ),
        ModelCard(
            id="brics-authority-alert-v1",
            name="Multilingual Authority Alert",
            version="1.0.0",
            module="backend/gemini/alerts.py",
            kind="gemini_reasoning",
            trained=False,
            task="multilingual_authority_coordination",
            input_layers=["L1-L4 fused via GeminiAQIAnalysis + optional GeminiCrossBorderEvent"],
            input_schema={
                "GeminiAQIAnalysis.risk_level": "str",
                "GeminiAQIAnalysis.health_advisory": "str",
                "GeminiCrossBorderEvent.source_cause": "str (optional)",
            },
            output_schema="AlertMessage",
            corridors=["All five — the cross-border coordination layer"],
            countries=["IN", "BR", "CN", "ZA"],
        ),
    ],
)
