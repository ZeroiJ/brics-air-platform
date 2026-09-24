"""Layer 1 — Government AQI via OpenAQ v3 (async, httpx).

Cities: Delhi, Mumbai, São Paulo, Beijing, Johannesburg.
Caches to backend/cache/openaq.json. Falls back to realistic mock data.
"""
from __future__ import annotations

import json
import os
from datetime import timezone
from pathlib import Path

import httpx

from backend.models import AQIReading, BRICS_CITIES, utcnow

CACHE_PATH = Path(__file__).parent.parent / "cache" / "openaq.json"
BASE_URL = "https://api.openaq.org/v3"
TIMEOUT = 15.0


# --- PM2.5 (µg/m³) -> US EPA AQI -------------------------------------------
# Breakpoints: (Cp_low, Cp_high, I_low, I_high)
_PM25_BREAKPOINTS = [
    (0.0, 12.0, 0, 50),
    (12.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 150.4, 151, 200),
    (150.5, 250.4, 201, 300),
    (250.5, 350.4, 301, 400),
    (350.5, 500.4, 401, 500),
]


def pm25_to_aqi(pm25: float) -> int:
    for c_lo, c_hi, i_lo, i_hi in _PM25_BREAKPOINTS:
        if pm25 <= c_hi:
            aqi = (i_hi - i_lo) / (c_hi - c_lo) * (pm25 - c_lo) + i_lo
            return int(round(aqi))
    return 500


def _headers() -> dict:
    key = os.getenv("OPENAQ_API_KEY", "").strip()
    return {"X-API-Key": key} if key else {}


async def _latest_for_coords(client: httpx.AsyncClient, lat: float, lng: float) -> dict:
    """Return {pm25, pm10, no2, so2} from nearest OpenAQ location.

    v3 /latest rows carry no parameter name, so map each row's sensorsId to a
    parameter via the location detail (one extra request per location).
    The newest-utc value wins per parameter (some stations' 'latest' is stale).
    """
    loc_resp = await client.get(
        f"{BASE_URL}/locations",
        params={"coordinates": f"{lat},{lng}", "radius": 25000, "limit": 5},
    )
    loc_resp.raise_for_status()
    locations = loc_resp.json().get("results", [])
    if not locations:
        raise ValueError("No OpenAQ locations nearby")

    merged: dict = {}
    best_stamp: dict[str, str] = {}
    for loc in locations[:3]:
        loc_id = loc.get("id")
        if loc_id is None:
            continue
        try:
            # sensor id -> parameter name for this location
            param_by_sensor: dict[int, str] = {}
            detail = await client.get(f"{BASE_URL}/locations/{loc_id}")
            if detail.status_code == 200:
                detail_loc = (detail.json().get("results") or [{}])[0]
                for sens in detail_loc.get("sensors") or []:
                    sid = sens.get("id")
                    pn = sens.get("parameter")
                    pname = (pn.get("name") if isinstance(pn, dict) else pn or "")
                    if sid is not None and pname:
                        param_by_sensor[sid] = str(pname).lower()
            s_resp = await client.get(f"{BASE_URL}/locations/{loc_id}/latest")
            if s_resp.status_code != 200:
                continue
            for row in s_resp.json().get("results", []):
                param = param_by_sensor.get(row.get("sensorsId"))
                if not param:
                    continue
                val = row.get("value")
                if val is None:
                    continue
                if param in ("pm25", "pm2.5"):
                    key = "pm25"
                elif param == "pm10":
                    key = "pm10"
                elif param == "no2":
                    key = "no2"
                elif param == "so2":
                    key = "so2"
                else:
                    continue
                stamp = str((row.get("datetime") or {}).get("utc") or "")
                if key not in merged or stamp > best_stamp.get(key, ""):
                    merged[key] = float(val)
                    best_stamp[key] = stamp
        except Exception:
            continue
        if "pm25" in merged and "pm10" in merged:
            break
    if "pm25" not in merged:
        raise ValueError("No PM2.5 measurement found")
    return merged


async def fetch_aqi_all() -> list[AQIReading]:
    api_key = os.getenv("OPENAQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAQ_API_KEY not set")
    readings: list[AQIReading] = []
    async with httpx.AsyncClient(headers=_headers(), timeout=TIMEOUT) as client:
        for c in BRICS_CITIES:
            try:
                vals = await _latest_for_coords(client, c["lat"], c["lng"])
            except Exception:
                readings.append(fallback_city(c["city"]))
                continue
            pm25 = vals.get("pm25", 0.0)
            readings.append(
                AQIReading(
                    city=c["city"],
                    country=c["country"],
                    lat=c["lat"],
                    lng=c["lng"],
                    aqi=pm25_to_aqi(pm25),
                    pm25=round(pm25, 1),
                    pm10=round(vals.get("pm10", pm25 * 1.6), 1),
                    no2=vals.get("no2"),
                    so2=vals.get("so2"),
                    source="openaq",
                    timestamp=utcnow(),
                )
            )
    save_cache(readings)
    return readings


async def fetch_city_aqi(city: str) -> AQIReading:
    all_readings = await fetch_aqi_all()
    for r in all_readings:
        if r.city.lower() == city.strip().lower():
            return r
    raise KeyError(f"City '{city}' not in BRICS set")


# --- Cache -----------------------------------------------------------------
def save_cache(readings: list[AQIReading]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps([r.model_dump(mode="json") for r in readings], indent=2))


def load_cache() -> list[AQIReading]:
    if not CACHE_PATH.exists():
        return fallback()
    try:
        raw = json.loads(CACHE_PATH.read_text())
        return [AQIReading(**r) for r in raw]
    except Exception:
        return fallback()


# --- Fallback (realistic, demo-safe) ----------------------------------------
_FALLBACK_ROWS = [
    # city, country, lat, lng, aqi, pm25, pm10, no2, so2
    ("Delhi", "India", 28.6139, 77.2090, 287, 237.0, 342.0, 68.0, 22.0),
    ("Mumbai", "India", 19.0760, 72.8777, 132, 48.5, 96.0, 34.0, 14.0),
    ("São Paulo", "Brazil", -23.5505, -46.6333, 68, 19.2, 34.0, 21.0, 6.0),
    ("Beijing", "China", 39.9042, 116.4074, 156, 68.4, 118.0, 52.0, 18.0),
    ("Johannesburg", "South Africa", -26.2041, 28.0473, 54, 12.8, 28.0, 16.0, 8.0),
]


def fallback() -> list[AQIReading]:
    ts = utcnow()
    return [
        AQIReading(
            city=city, country=country, lat=lat, lng=lng, aqi=aqi,
            pm25=pm25, pm10=pm10, no2=no2, so2=so2,
            source="mock", timestamp=ts,
        )
        for city, country, lat, lng, aqi, pm25, pm10, no2, so2 in _FALLBACK_ROWS
    ]


def fallback_city(city: str) -> AQIReading:
    for r in fallback():
        if r.city.lower() == city.strip().lower():
            return r
    raise KeyError(f"Unknown city '{city}'")
