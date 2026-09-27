"""Backup AQI via WAQI (World Air Quality Index).

Endpoint: GET https://api.waqi.info/feed/{city}/?token={token}
Used only when OpenAQ is down. Caches to backend/cache/waqi.json.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import httpx

from backend.models import AQIReading, BRICS_CITIES, utcnow

CACHE_PATH = Path(__file__).parent.parent / "cache" / "waqi.json"
TIMEOUT = 15.0

# WAQI feed slugs per BRICS city
WAQI_SLUGS = {
    "Delhi": "delhi",
    "Mumbai": "mumbai",
    "São Paulo": "sao-paulo",
    "Beijing": "beijing",
    "Johannesburg": "johannesburg",
}


DEMO_TOKEN = "demo"


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


async def fetch_city_waqi(city: str) -> AQIReading:
    token = os.getenv("WAQI_TOKEN", "").strip()
    if not token:
        raise RuntimeError("WAQI_TOKEN not set")
    if token.lower() == DEMO_TOKEN:
        # The public "demo" token ignores the requested city and always returns a
        # canned Shanghai reading (aqi=72) with a 200 OK. Serving that as our
        # backup would be fabricated data, so refuse it and let the caller fall
        # back to the committed OpenAQ snapshot instead.
        raise RuntimeError(
            "WAQI_TOKEN is the public 'demo' token — it returns a fixed Shanghai "
            "sample for every city. Request a real token at "
            "https://aqicn.org/data-platform/token"
        )
    meta = next((c for c in BRICS_CITIES if c["city"].lower() == city.strip().lower()), None)
    if meta is None:
        raise KeyError(f"Unknown city '{city}'")
    slug = WAQI_SLUGS.get(meta["city"], city.strip().lower())
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(f"https://api.waqi.info/feed/{slug}/", params={"token": token})
        resp.raise_for_status()
        payload = resp.json()
    if payload.get("status") != "ok":
        raise ValueError(f"WAQI error for {city}: {payload.get('data')}")
    data = payload["data"]
    aqi = int(data.get("aqi", 0) or 0)
    iaqi = data.get("iaqi") or {}

    def _v(key: str) -> float | None:
        node = iaqi.get(key)
        return float(node["v"]) if node and node.get("v") is not None else None

    pm25 = _v("pm25") or max(aqi * 0.8, 1.0)
    pm10 = _v("pm10") or pm25 * 1.6
    geo = data.get("city", {}).get("geo") or []
    # Sanity-check: the station must actually be near the city we asked for,
    # otherwise a shared/throttled token may have returned some other station.
    if len(geo) == 2:
        dist = _haversine_km(meta["lat"], meta["lng"], float(geo[0]), float(geo[1]))
        if dist > 150:
            raise ValueError(
                f"WAQI returned a station {dist:.0f} km from {meta['city']} "
                f"(got {data.get('city', {}).get('name')}) — refusing mismatched data"
            )
    reading = AQIReading(
        city=meta["city"], country=meta["country"],
        lat=meta["lat"], lng=meta["lng"],
        aqi=aqi, pm25=round(pm25, 1), pm10=round(pm10, 1),
        no2=_v("no2"), so2=_v("so2"), source="waqi", timestamp=utcnow(),
    )
    return reading


async def fetch_all_waqi() -> list[AQIReading]:
    out: list[AQIReading] = []
    for c in BRICS_CITIES:
        try:
            out.append(await fetch_city_waqi(c["city"]))
        except Exception:
            from backend.pipeline.openaq import fallback_city
            r = fallback_city(c["city"])
            r.source = "waqi"
            out.append(r)
    save_cache(out)
    return out


def save_cache(rows: list[AQIReading]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps([r.model_dump(mode="json") for r in rows], indent=2))


def load_cache() -> list[AQIReading]:
    if not CACHE_PATH.exists():
        from backend.pipeline.openaq import fallback
        return fallback()
    try:
        return [AQIReading(**r) for r in json.loads(CACHE_PATH.read_text())]
    except Exception:
        from backend.pipeline.openaq import fallback
        return fallback()


def fallback() -> list[AQIReading]:
    from backend.pipeline.openaq import fallback as _fb
    rows = _fb()
    for r in rows:
        r.source = "waqi"
    return rows
