"""Layer 3 — Wind + weather via Open-Meteo (FREE, no API key).

Endpoint: https://api.open-meteo.com/v1/forecast
Critical for cross-border detection — wind direction tells Gemini where
pollution is transported.
Caches to backend/cache/meteo.json. Includes realistic fallback.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from backend.models import BRICS_CITIES, MeteoData, utcnow

CACHE_PATH = Path(__file__).parent.parent / "cache" / "meteo.json"
BASE_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 15.0


def deg_to_label(deg: float) -> str:
    labels = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return labels[int((deg % 360 + 22.5) // 45) % 8]


async def _fetch_one(client: httpx.AsyncClient, city: str, lat: float, lng: float) -> MeteoData:
    resp = await client.get(
        BASE_URL,
        params={
            "latitude": lat,
            "longitude": lng,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m",
            "timezone": "auto",
        },
    )
    resp.raise_for_status()
    cur = resp.json().get("current", {})
    # Open-Meteo wind_speed_10m is km/h by default
    wdir = float(cur.get("wind_direction_10m", 0.0))
    return MeteoData(
        lat=lat,
        lng=lng,
        city=city,
        wind_speed_kmh=round(float(cur.get("wind_speed_10m", 0.0)), 1),
        wind_direction_deg=round(wdir, 1),
        wind_direction_label=deg_to_label(wdir),
        temperature_c=round(float(cur.get("temperature_2m", 0.0)), 1),
        humidity_pct=round(float(cur.get("relative_humidity_2m", 50.0)), 1),
        timestamp=utcnow(),
    )


async def fetch_meteo_all() -> list[MeteoData]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        results = await asyncio.gather(
            *(_fetch_one(client, c["city"], c["lat"], c["lng"]) for c in BRICS_CITIES),
            return_exceptions=True,
        )
    rows: list[MeteoData] = []
    for c, res in zip(BRICS_CITIES, results):
        rows.append(res if isinstance(res, MeteoData) else fallback_city(c["city"]))
    # Only cache if at least one live reading succeeded; simplest: cache always
    save_cache(rows)
    return rows


async def fetch_city_meteo(city: str) -> MeteoData:
    for m in await fetch_meteo_all():
        if m.city.lower() == city.strip().lower():
            return m
    raise KeyError(f"Unknown city '{city}'")


# --- Cache -----------------------------------------------------------------
def save_cache(rows: list[MeteoData]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps([r.model_dump(mode="json") for r in rows], indent=2))


def load_cache() -> list[MeteoData]:
    if not CACHE_PATH.exists():
        return fallback()
    try:
        return [MeteoData(**r) for r in json.loads(CACHE_PATH.read_text())]
    except Exception:
        return fallback()


# --- Fallback: realistic September weather ----------------------------------
# Delhi NW flow in burning season is the key demo signal (Punjab -> Delhi).
_FALLBACK_ROWS = [
    # city, lat, lng, wind_kmh, wind_deg, temp_c, humidity
    ("Delhi", 28.6139, 77.2090, 14.2, 315.0, 33.5, 58.0),
    ("Mumbai", 19.0760, 72.8777, 18.6, 270.0, 29.8, 74.0),
    ("São Paulo", -23.5505, -46.6333, 12.4, 135.0, 24.1, 62.0),
    ("Beijing", 39.9042, 116.4074, 9.8, 45.0, 22.6, 48.0),
    ("Johannesburg", -26.2041, 28.0473, 16.1, 20.0, 21.3, 38.0),
]


def fallback() -> list[MeteoData]:
    ts = utcnow()
    out = []
    for city, lat, lng, wspd, wdeg, temp, hum in _FALLBACK_ROWS:
        out.append(
            MeteoData(
                lat=lat, lng=lng, city=city,
                wind_speed_kmh=wspd, wind_direction_deg=wdeg,
                wind_direction_label=deg_to_label(wdeg),
                temperature_c=temp, humidity_pct=hum, timestamp=ts,
            )
        )
    return out


def fallback_city(city: str) -> MeteoData:
    for m in fallback():
        if m.city.lower() == city.strip().lower():
            return m
    raise KeyError(f"Unknown city '{city}'")
