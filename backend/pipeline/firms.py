"""Layer 2 — NASA FIRMS fire hotspots (VIIRS_SNPP_NRT, sync via requests).

BBoxes: South Asia (60,5,100,40), South America (-80,-40,-30,10).
Caches to backend/cache/firms.json. Includes demo fallback with
Punjab crop-burning + Amazon clusters.
"""
from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

from backend.models import FireHotspot, utcnow

CACHE_PATH = Path(__file__).parent.parent / "cache" / "firms.json"
TIMEOUT = 20

BBOXES = {
    "south_asia": "60,5,100,40",
    "south_america": "-80,-40,-30,10",
}
PRODUCT = "VIIRS_SNPP_NRT"
DAY_RANGE = 2  # last 2 days


def _bbox_url(key: str, bbox: str) -> str:
    return f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{PRODUCT}/{bbox}/{DAY_RANGE}"


def _country_for(lat: float, lng: float) -> str:
    if 60 <= lng <= 100 and 5 <= lat <= 40:
        if 28 <= lat <= 33 and 73 <= lng <= 78:
            return "India"  # Punjab burning belt
        if 24 <= lat <= 37 and 60 <= lng <= 75:
            return "Pakistan"
        return "India"
    if -80 <= lng <= -30 and -40 <= lat <= 10:
        if -15 <= lat <= 5 and -70 <= lng <= -45:
            return "Brazil"  # Amazon
        return "Brazil"
    return "Unknown"


def _parse_csv(text: str) -> list[FireHotspot]:
    reader = csv.DictReader(io.StringIO(text))
    out: list[FireHotspot] = []
    for row in reader:
        try:
            lat = float(row.get("latitude", ""))
            lng = float(row.get("longitude", ""))
            bright = float(row.get("bright_ti4", row.get("brightness", 300.0)))
            frp = float(row.get("frp", 5.0))
            sat_raw = (row.get("satellite", "N") or "N").upper()
            satellite = "VIIRS" if "VIIRS" in sat_raw or sat_raw in ("N", "NOAA-20", "NOAA20", "SNPP") else sat_raw[:5]
            if satellite not in ("VIIRS", "MODIS"):
                satellite = "VIIRS"
            date = row.get("acq_date", "")
            time = row.get("acq_time", "0000").zfill(4)
            try:
                detected = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
            except Exception:
                detected = utcnow()
            out.append(FireHotspot(
                lat=lat, lng=lng, brightness=bright, frp=frp,
                country=_country_for(lat, lng), detected_at=detected,
                satellite=satellite,
            ))
        except (ValueError, TypeError):
            continue
    return out


def fetch_fires(limit: int = 300) -> list[FireHotspot]:
    key = os.getenv("FIRMS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("FIRMS_API_KEY not set")
    # Per-region quota: South America returns 5k-12k rows, so a global top-N by
    # FRP would evict every South Asian hotspot (Punjab crop-burning belt) and
    # the cross-border demo could never trigger. Cap each region separately.
    per_region = max(1, limit // 2)
    hotspots: list[FireHotspot] = []
    for _name, bbox in BBOXES.items():
        resp = requests.get(_bbox_url(key, bbox), timeout=TIMEOUT)
        resp.raise_for_status()
        if resp.text.strip().startswith(("Invalid", "Error", "<")):
            continue
        rows = _parse_csv(resp.text)
        rows.sort(key=lambda h: h.frp, reverse=True)
        hotspots.extend(rows[:per_region])
    if not hotspots:
        raise ValueError("FIRMS returned zero hotspots")
    hotspots.sort(key=lambda h: h.frp, reverse=True)
    save_cache(hotspots)
    return hotspots


# --- Cache -----------------------------------------------------------------
def save_cache(hotspots: list[FireHotspot]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps([h.model_dump(mode="json") for h in hotspots], indent=2))


def load_cache() -> list[FireHotspot]:
    if not CACHE_PATH.exists():
        return fallback()
    try:
        return [FireHotspot(**r) for r in json.loads(CACHE_PATH.read_text())]
    except Exception:
        return fallback()


# --- Fallback: Punjab cluster + Amazon cluster ------------------------------
def fallback() -> list[FireHotspot]:
    ts = utcnow()
    rows = [
        # Punjab crop-burning belt (upwind of Delhi, NW)
        (30.90, 75.85, 342.5, 18.4, "India"),
        (30.65, 76.10, 335.1, 12.7, "India"),
        (31.10, 75.40, 351.8, 24.9, "India"),
        (30.35, 76.45, 328.6, 9.3, "India"),
        (29.80, 76.90, 331.2, 11.1, "India"),
        (31.55, 74.95, 339.0, 15.6, "Pakistan"),
        # Amazon corridor (upwind of São Paulo)
        (-8.45, -63.20, 361.4, 42.5, "Brazil"),
        (-9.10, -62.55, 355.9, 31.2, "Brazil"),
        (-7.80, -64.10, 348.3, 22.8, "Brazil"),
        (-10.25, -61.40, 340.7, 17.5, "Brazil"),
        # Mpumalanga (upwind of Johannesburg)
        (-26.05, 29.25, 333.4, 10.8, "South Africa"),
        (-25.70, 29.80, 329.1, 7.6, "South Africa"),
    ]
    return [
        FireHotspot(lat=la, lng=ln, brightness=b, frp=f, country=c,
                    detected_at=ts, satellite="VIIRS")
        for la, ln, b, f, c in rows
    ]
