"""Shared Pydantic schemas — Sujal owns this file.

Every module (pipeline, gemini, frontend) uses these exact shapes.
Sarthak + Anoushka: import from backend.models, do not redefine.
"""
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Canonical BRICS cities (single source of truth for lat/lng)
# ---------------------------------------------------------------------------
BRICS_CITIES: list[dict] = [
    {"city": "Delhi", "country": "India", "lat": 28.6139, "lng": 77.2090},
    {"city": "Mumbai", "country": "India", "lat": 19.0760, "lng": 72.8777},
    {"city": "São Paulo", "country": "Brazil", "lat": -23.5505, "lng": -46.6333},
    {"city": "Beijing", "country": "China", "lat": 39.9042, "lng": 116.4074},
    {"city": "Johannesburg", "country": "South Africa", "lat": -26.2041, "lng": 28.0473},
]

CITY_LOOKUP: dict[str, dict] = {c["city"].lower(): c for c in BRICS_CITIES}


def lookup_city(city: str) -> dict:
    """Case-insensitive city lookup. Raises KeyError if unknown."""
    key = city.strip().lower()
    if key not in CITY_LOOKUP:
        raise KeyError(f"Unknown city '{city}'. Choose from: {[c['city'] for c in BRICS_CITIES]}")
    return CITY_LOOKUP[key]


# ---------------------------------------------------------------------------
# Layer 1 — AQI sensor data (government + citizen sensors share this shape)
# ---------------------------------------------------------------------------
class AQIReading(BaseModel):
    city: str
    country: str
    lat: float
    lng: float
    aqi: int = Field(ge=0, le=1000)
    pm25: float = Field(ge=0)
    pm10: float = Field(ge=0)
    no2: Optional[float] = None
    so2: Optional[float] = None
    source: str = Field(description='"openaq" | "waqi" | "cpcb" | "sensor_community" | "mock"')
    timestamp: datetime


# ---------------------------------------------------------------------------
# Layer 2 — Fire/smoke from satellite (NASA FIRMS)
# ---------------------------------------------------------------------------
class FireHotspot(BaseModel):
    lat: float
    lng: float
    brightness: float
    frp: float = Field(description="Fire Radiative Power in MW")
    country: str
    detected_at: datetime
    satellite: str = Field(description='"VIIRS" | "MODIS"')


# ---------------------------------------------------------------------------
# Layer 3 — Meteorological (Open-Meteo)
# ---------------------------------------------------------------------------
class MeteoData(BaseModel):
    lat: float
    lng: float
    city: str
    wind_speed_kmh: float = Field(ge=0)
    wind_direction_deg: float = Field(ge=0, le=360)
    wind_direction_label: str = Field(description='Cardinal label: N/NE/E/SE/S/SW/W/NW')
    temperature_c: float
    humidity_pct: float = Field(ge=0, le=100)
    timestamp: datetime


# ---------------------------------------------------------------------------
# Layer 4 — Citizen input
# ---------------------------------------------------------------------------
class CitizenPhoto(BaseModel):
    city: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    image_base64: str
    uploaded_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# Gemini outputs — Sarthak produces these
# ---------------------------------------------------------------------------
class GeminiAQIAnalysis(BaseModel):
    city: str
    risk_level: str
    primary_pollutant: str
    health_advisory: str
    likely_sources: list[str]
    cross_border_suspected: bool
    cross_border_contribution_pct: float
    confidence: float


class GeminiForecast(BaseModel):
    city: str
    current_aqi: int
    forecast_6h_aqi: int
    forecast_24h_aqi: int
    spike_warning: bool
    spike_cause: str
    forecast_confidence: float


class GeminiCrossBorderEvent(BaseModel):
    source_country: str
    source_city: str
    source_cause: str = Field(description='"crop burning" | "industrial" | "wildfire" | ...')
    affected_city: str
    affected_country: str
    transport_direction: str
    distance_km: float
    severity: str
    evidence_summary: str


class GeminiPhotoResult(BaseModel):
    pollution_visible: bool
    pollution_type: str
    estimated_aqi_category: str
    visibility_km: float
    severity_score: int = Field(ge=1, le=10)
    likely_source: str
    recommendation: str
    confidence: float


class AlertMessage(BaseModel):
    city: str
    risk_level: str
    message_hindi: str
    message_portuguese: str
    message_english: str
    target_authority: str
    urgency: str = Field(description='"immediate" | "advisory" | "watch"')


# ---------------------------------------------------------------------------
# Federation — PS: "designed for interoperability so BRICS nations can share
# predictive models and coordinate resources".
#
# A ModelCard is a *contract*, not a trained artifact. It declares the wire
# format (inputs, output schema, corridors, countries) of a reasoning module
# already deployed on this node, so another BRICS node could consume the same
# interface without re-deriving it. The `trained` flag is explicit and always
# False: this project trains no models (work-division.md anti-patterns), and
# claiming otherwise would be fabricated data.
# ---------------------------------------------------------------------------


class ModelCard(BaseModel):
    id: str
    name: str
    version: str
    module: str = Field(description="In-repo module implementing this contract")
    kind: str = Field(description='"gemini_reasoning" | "rule_based_heuristic"')
    trained: bool = Field(description="Always False — no custom model training in this project")
    task: str
    input_layers: list[str] = Field(description="PS data layers consumed (L1 gov AQI, L2 satellite, L3 meteo, L4 citizen)")
    input_schema: dict[str, str] = Field(description="field -> type, as consumed by this contract")
    output_schema: str = Field(description="Name of the Pydantic model returned")
    corridors: list[str]
    countries: list[str]
    transport: str = Field(default="REST/JSON")
    license: str = Field(default="MIT")
    shareable: bool = True


class FederationRegistry(BaseModel):
    protocol: str
    node: str
    note: str
    models: list[ModelCard]
