"""FastAPI backbone — Sujal.

Serves all four data layers + AI-backed endpoints.
Design: live fetch -> cache -> hardcoded fallback (never 500 during demo).
Gemini modules (Sarthak) are optional: if importable AND GEMINI_API_KEY is set,
they are used; otherwise deterministic rule-based fallbacks return valid schemas
so Anoushka's frontend works end-to-end right now.

Run: uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import asyncio
import base64
import math
import os
import time
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv()

from backend.models import (  # noqa: E402
    AlertMessage,
    AQIReading,
    BRICS_CITIES,
    CitizenPhoto,
    FireHotspot,
    GeminiAQIAnalysis,
    GeminiCrossBorderEvent,
    GeminiForecast,
    GeminiPhotoResult,
    MeteoData,
    lookup_city,
    utcnow,
)

# --- Pipeline imports (Sujal) ------------------------------------------------
from backend.pipeline import meteo as meteo_mod  # noqa: E402
from backend.pipeline import openaq as openaq_mod  # noqa: E402

try:
    from backend.pipeline import firms as firms_mod  # noqa: E402
except Exception:  # pragma: no cover
    firms_mod = None
try:
    from backend.pipeline import sensor_community as sensors_mod  # noqa: E402
except Exception:  # pragma: no cover
    sensors_mod = None
try:
    from backend.pipeline import waqi as waqi_mod  # noqa: E402
except Exception:  # pragma: no cover
    waqi_mod = None

# --- Gemini imports (Sarthak — optional until his modules land) ---------------
_gemini_available = bool(os.getenv("GEMINI_API_KEY", "").strip())
try:
    from backend.gemini import aqi_analysis as gem_aqi  # type: ignore
except Exception:
    gem_aqi = None
try:
    from backend.gemini import forecast as gem_forecast  # type: ignore
except Exception:
    gem_forecast = None
try:
    from backend.gemini import crossborder as gem_cross  # type: ignore
except Exception:
    gem_cross = None
try:
    from backend.gemini import alerts as gem_alerts  # type: ignore
except Exception:
    gem_alerts = None
try:
    from backend.gemini import photo_analysis as gem_photo  # type: ignore
except Exception:
    gem_photo = None


def _use_gemini(module) -> bool:
    return _gemini_available and module is not None and hasattr(module, "__call__")


def _cache_state(module, env_var: str) -> tuple[str, str]:
    """Resilience status for key-gated sources.

    Returns (status, detail): "live" | "cached" | "fallback".
    A cache file only exists if a real fetch saved it — fallback() never writes.
    """
    if module is None:
        return "unavailable", f"{env_var} module not importable"
    key = os.getenv(env_var, "").strip()
    cache = getattr(module, "CACHE_PATH", None)
    has_cache = cache is not None and cache.exists()
    if key and has_cache:
        age_h = (time.time() - cache.stat().st_mtime) / 3600
        if age_h <= 24:
            return "live", f"{env_var} set, snapshot {age_h:.1f}h old"
        return "cached", f"{env_var} set but snapshot {age_h:.1f}h old"
    if has_cache:
        return "cached", f"no {env_var} — serving committed snapshot"
    return "fallback", f"no {env_var} — serving hardcoded fallback"


def _gemini_status() -> tuple[str, str]:
    modules = [gem_aqi, gem_forecast, gem_cross, gem_alerts, gem_photo]
    present = sum(m is not None for m in modules)
    if _gemini_available and present == 5:
        return "live", f"GEMINI_API_KEY set, {present}/5 modules wired (gemini-3.6-flash)"
    if _gemini_available:
        return "degraded", f"GEMINI_API_KEY set but {present}/5 modules importable"
    return "fallback", "no GEMINI_API_KEY — rule-based stand-ins active"


app = FastAPI(title="BRICS Climate Intelligence Platform", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===========================================================================
# Helpers — resilient data loading (live -> cache -> fallback)
# ===========================================================================
# Short in-process TTL so ONE page load / one demo click causes ONE upstream
# fetch per source, not one per endpoint. Without this, /api/analysis +
# /api/forecast + /api/crossborder + /api/fires all re-hit FIRMS concurrently.
_MEM: dict[str, tuple[float, object]] = {}


async def _memo(key: str, factory, ttl: float = 120.0):
    now = time.time()
    hit = _MEM.get(key)
    if hit is not None and now - hit[0] < ttl:
        return hit[1]
    val = await factory()
    _MEM[key] = (time.time(), val)
    return val


async def _with_timeout(coro, seconds: float = 12.0):
    return await asyncio.wait_for(coro, timeout=seconds)


async def _fetch_aqi_all() -> list[AQIReading]:
    try:
        return await _with_timeout(openaq_mod.fetch_aqi_all(), seconds=30.0)
    except Exception:
        pass
    # WAQI live backup first when a token is set: openaq.load_cache() never
    # returns empty (it falls back to mock), so WAQI was previously unreachable.
    if waqi_mod is not None and os.getenv("WAQI_TOKEN", "").strip():
        try:
            return await _with_timeout(waqi_mod.fetch_all_waqi())
        except Exception:
            pass
    try:
        cached = openaq_mod.load_cache()
        if cached:
            return cached
    except Exception:
        pass
    return openaq_mod.fallback()


async def get_aqi_all() -> list[AQIReading]:
    return await _memo("aqi_all", _fetch_aqi_all, ttl=120.0)


async def get_aqi_city(city: str) -> AQIReading:
    lookup_city(city)  # validates, raises KeyError -> 404
    for r in await get_aqi_all():
        if r.city.lower() == city.strip().lower():
            return r
    return openaq_mod.fallback_city(city)


async def _fetch_fires() -> list[FireHotspot]:
    """Serve the last snapshot immediately; revalidate FIRMS in the background.

    FIRMS area queries return 5k-12k CSV rows (10-30s download). Blocking the
    request on that made every dashboard load crawl, so the committed snapshot
    is served at once and refreshed out-of-band for the next request.
    """
    if firms_mod is None:
        return []
    try:
        cached = firms_mod.load_cache()
    except Exception:
        cached = []
    if cached:
        if not _MEM.get("fires_refreshing"):
            task = asyncio.create_task(_refresh_fires())
            _MEM["fires_refreshing"] = task
            task.add_done_callback(lambda t: _MEM.pop("fires_refreshing", None))
        return cached
    try:
        return await asyncio.to_thread(firms_mod.fetch_fires)
    except Exception:
        return firms_mod.fallback()


async def _refresh_fires() -> None:
    try:
        rows = await asyncio.to_thread(firms_mod.fetch_fires)
        _MEM["fires"] = (time.time(), rows)
    except Exception:
        pass


async def get_fires() -> list[FireHotspot]:
    return await _memo("fires", _fetch_fires, ttl=60.0)


async def _fetch_meteo_all() -> list[MeteoData]:
    try:
        return await _with_timeout(meteo_mod.fetch_meteo_all())
    except Exception:
        pass
    try:
        cached = meteo_mod.load_cache()
        if cached:
            return cached
    except Exception:
        pass
    return meteo_mod.fallback()


async def get_meteo_all() -> list[MeteoData]:
    return await _memo("meteo_all", _fetch_meteo_all, ttl=120.0)


async def get_meteo_city(city: str) -> MeteoData:
    lookup_city(city)
    for m in await get_meteo_all():
        if m.city.lower() == city.strip().lower():
            return m
    return meteo_mod.fallback_city(city)


async def _fetch_sensors(country: str | None = None) -> list[AQIReading]:
    if sensors_mod is not None:
        try:
            rows = await asyncio.to_thread(sensors_mod.fetch_sensors, country)
            if rows:
                return rows
        except Exception:
            pass
        try:
            cached = sensors_mod.load_cache()
            if country:
                code = country.strip().upper()
                city_map = {k: v[0] for k, v in sensors_mod.COUNTRIES.items()}
                # filter cache by country code mapping
                wanted = {v[0].lower() for k, v in sensors_mod.COUNTRIES.items() if k == code}
                filt = [r for r in cached if r.city.lower() in wanted or not wanted]
                if filt:
                    return filt
            elif cached:
                return cached
        except Exception:
            pass
        return sensors_mod.fallback()
    return []


async def get_sensors(country: str | None = None) -> list[AQIReading]:
    key = f"sensors_{country or 'ALL'}"
    return await _memo(key, lambda: _fetch_sensors(country), ttl=120.0)


# ===========================================================================
# Rule-based fallbacks for Gemini outputs (used until Sarthak's modules land)
# ===========================================================================
def _risk(aqi: int) -> str:
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Moderate"
    if aqi <= 200:
        return "Poor"
    if aqi <= 300:
        return "Very Poor"
    return "Severe"


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


AUTHORITIES = {
    "Delhi": "Delhi Pollution Control Committee",
    "Mumbai": "Maharashtra Pollution Control Board",
    "São Paulo": "CETESB São Paulo",
    "Beijing": "Beijing Municipal Ecology and Environment Bureau",
    "Johannesburg": "City of Johannesburg Air Quality Unit",
}


def rule_analysis(reading: AQIReading, meteo: MeteoData, fires: list[FireHotspot]) -> GeminiAQIAnalysis:
    nearby = [f for f in fires if _haversine_km(reading.lat, reading.lng, f.lat, f.lng) < 500]
    max_frp = max((f.frp for f in nearby), default=0.0)
    cross = len(nearby) >= 2 and max_frp > 8.0
    contrib = min(85.0, round(len(nearby) * 8.0 + max_frp * 0.8, 1)) if cross else round(min(20.0, len(nearby) * 5.0), 1)
    sources: list[str] = []
    if reading.pm25 > 55:
        sources.append("agricultural burning" if nearby else "traffic + industrial")
    if reading.pm25 > 35:
        sources.append("industrial emissions")
    if meteo.wind_speed_kmh < 10:
        sources.append("stagnant meteorology (low dispersion)")
    if not sources:
        sources = ["traffic", "local sources"]
    risk = _risk(reading.aqi)
    advisory = {
        "Good": "Air quality satisfactory. Enjoy outdoor activities.",
        "Moderate": "Sensitive groups should limit prolonged outdoor exertion.",
        "Poor": "Everyone may feel effects. Limit outdoor activity, wear N95 outdoors.",
        "Very Poor": "Health alert: avoid outdoor exertion, keep windows closed, use air purifiers.",
        "Severe": "Emergency: stay indoors, N95 mandatory outside, follow authority orders.",
    }[risk]
    return GeminiAQIAnalysis(
        city=reading.city, risk_level=risk,
        primary_pollutant="PM2.5" if reading.pm25 / max(reading.pm10, 1) > 0.4 else "PM10",
        health_advisory=advisory, likely_sources=sources,
        cross_border_suspected=cross, cross_border_contribution_pct=contrib,
        confidence=0.72 if cross else 0.65,
    )


def rule_forecast(reading: AQIReading, meteo: MeteoData, fires: list[FireHotspot]) -> GeminiForecast:
    nearby = [f for f in fires if _haversine_km(reading.lat, reading.lng, f.lat, f.lng) < 500]
    fire_push = sum(f.frp for f in nearby[:10]) * 0.35
    stagnation = 12 if meteo.wind_speed_kmh < 10 else (-8 if meteo.wind_speed_kmh > 20 else 0)
    d6 = int(round(fire_push * 0.4 + stagnation * 0.4))
    d24 = int(round(fire_push * 0.9 + stagnation * 0.8))
    f6 = max(10, reading.aqi + d6)
    f24 = max(10, reading.aqi + d24)
    spike = f24 >= reading.aqi + 30 or f24 > 200
    cause = (
        f"{len(nearby)} active fires within 500km (max FRP {max((f.frp for f in nearby), default=0):.1f} MW) "
        f"with {meteo.wind_speed_kmh} km/h {meteo.wind_direction_label} winds transporting smoke"
        if spike and nearby else
        ("Stagnant winds limiting dispersion" if spike else "Stable conditions, no major transport expected")
    )
    return GeminiForecast(
        city=reading.city, current_aqi=reading.aqi,
        forecast_6h_aqi=f6, forecast_24h_aqi=f24,
        spike_warning=spike, spike_cause=cause, forecast_confidence=0.68,
    )


def rule_crossborder(
    readings: list[AQIReading], fires: list[FireHotspot], meteos: list[MeteoData]
) -> list[GeminiCrossBorderEvent]:
    events: list[GeminiCrossBorderEvent] = []
    # Demo corridors: Punjab fires + NW wind -> Delhi; Amazon fires -> São Paulo
    punjab = [f for f in fires if 28 <= f.lat <= 33 and 73 <= f.lng <= 78]
    amazon = [f for f in fires if -15 <= f.lat <= 5 and -70 <= f.lng <= -45]
    delhi_m = next((m for m in meteos if m.city == "Delhi"), None)
    if punjab and delhi_m and delhi_m.wind_direction_label in ("NW", "N", "W"):
        dist = _haversine_km(30.9, 75.85, 28.6139, 77.2090)
        events.append(GeminiCrossBorderEvent(
            source_country="India", source_city="Punjab burning belt",
            source_cause="crop burning", affected_city="Delhi",
            affected_country="India", transport_direction="NW → SE",
            distance_km=round(dist, 1), severity="high",
            evidence_summary=(
                f"{len(punjab)} VIIRS hotspots in Punjab (max FRP "
                f"{max(f.frp for f in punjab):.1f} MW), Delhi wind {delhi_m.wind_speed_kmh} km/h "
                f"from {delhi_m.wind_direction_label}, Delhi AQI elevated."
            ),
        ))
    sp_m = next((m for m in meteos if m.city == "São Paulo"), None)
    if amazon and sp_m:
        dist = _haversine_km(-8.45, -63.20, -23.5505, -46.6333)
        events.append(GeminiCrossBorderEvent(
            source_country="Brazil", source_city="Amazon basin",
            source_cause="wildfire", affected_city="São Paulo",
            affected_country="Brazil", transport_direction="NW → SE",
            distance_km=round(dist, 1), severity="moderate",
            evidence_summary=(
                f"{len(amazon)} VIIRS hotspots in Amazon corridor (max FRP "
                f"{max(f.frp for f in amazon):.1f} MW), São Paulo wind {sp_m.wind_speed_kmh} km/h "
                f"from {sp_m.wind_direction_label}."
            ),
        ))
    # India -> Pakistan corridor (Indo-Gangetic Plain): crop-burning east of the
    # border + easterly flow carries smoke toward Lahore. Demo step 3.
    lahore = (31.5497, 74.3436)
    border_fires = [f for f in fires if 30.0 <= f.lat <= 33.0 and 73.0 <= f.lng <= 76.5]
    delhi_m = next((m for m in meteos if m.city == "Delhi"), None)
    blowing_west = delhi_m is not None and delhi_m.wind_direction_label in ("E", "NE", "SE", "S")
    if border_fires and delhi_m and blowing_west:
        dist = _haversine_km(31.10, 75.40, *lahore)
        events.append(GeminiCrossBorderEvent(
            source_country="India", source_city="Punjab/Amritsar border belt",
            source_cause="crop burning", affected_city="Lahore",
            affected_country="Pakistan",
            transport_direction=f"{delhi_m.wind_direction_label} → W",
            distance_km=round(dist, 1), severity="high",
            evidence_summary=(
                f"{len(border_fires)} VIIRS hotspots in the Punjab border belt (max FRP "
                f"{max(f.frp for f in border_fires):.1f} MW), Delhi wind {delhi_m.wind_speed_kmh} km/h "
                f"from {delhi_m.wind_direction_label} transporting smoke northwest toward Lahore."
            ),
        ))
    return events


def rule_alert(analysis: GeminiAQIAnalysis, event: GeminiCrossBorderEvent | None) -> AlertMessage:
    src = f" Cross-border source: {event.source_cause} in {event.source_city}." if event else ""
    en = f"{analysis.city} AQI alert — {analysis.risk_level} ({analysis.primary_pollutant}). {analysis.health_advisory}{src}"
    hi = (
        f"{analysis.city} वायु गुणवत्ता चेतावनी — {analysis.risk_level} ({analysis.primary_pollutant})। "
        f"{analysis.health_advisory}{(' सीमा-पार स्रोत: ' + event.source_cause + ', ' + event.source_city + '।') if event else ''} "
        f"कृपया मास्क पहनें और अनावश्यक बाहर निकलने से बचें।"
    )
    pt = (
        f"Alerta de qualidade do ar em {analysis.city} — {analysis.risk_level} ({analysis.primary_pollutant}). "
        f"{analysis.health_advisory}{(' Fonte transfronteiriça: ' + event.source_cause + ' em ' + event.source_city + '.') if event else ''} "
        f"Evite esforço ao ar livre e siga as orientações das autoridades."
    )
    urgency = "immediate" if analysis.risk_level in ("Very Poor", "Severe") else ("advisory" if analysis.risk_level == "Poor" else "watch")
    return AlertMessage(
        city=analysis.city, risk_level=analysis.risk_level,
        message_hindi=hi, message_portuguese=pt, message_english=en,
        target_authority=AUTHORITIES.get(analysis.city, "Municipal Environment Authority"),
        urgency=urgency,
    )


# ===========================================================================
# Routes
# ===========================================================================
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/aqi", response_model=list[AQIReading])
async def api_aqi(city: str | None = Query(default=None)):
    rows = await get_aqi_all()
    if city:
        lookup_city(city)
        filt = [r for r in rows if r.city.lower() == city.strip().lower()]
        if not filt:
            return JSONResponse(status_code=404, content={"detail": f"Unknown city '{city}'"})
        return filt
    return rows


@app.get("/api/fires", response_model=list[FireHotspot])
async def api_fires(limit: int = Query(default=300, le=1000)):
    fires = await get_fires()
    return fires[:limit]


@app.get("/api/meteo")
async def api_meteo(city: str | None = Query(default=None)):
    if city:
        lookup_city(city)
        return await get_meteo_city(city)
    return await get_meteo_all()


@app.get("/api/sensors", response_model=list[AQIReading])
async def api_sensors(country: str | None = Query(default=None)):
    return await get_sensors(country)


@app.get("/api/analysis", response_model=GeminiAQIAnalysis)
async def api_analysis(city: str = Query(...)):
    reading = await get_aqi_city(city)
    meteo = await get_meteo_city(reading.city)
    if gem_aqi is not None and _gemini_available:
        try:
            result = gem_aqi.analyze_aqi(reading, meteo)  # type: ignore[attr-defined]
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except Exception:
            pass
    fires = await get_fires()
    return rule_analysis(reading, meteo, fires)


@app.get("/api/forecast", response_model=GeminiForecast)
async def api_forecast(city: str = Query(...)):
    reading = await get_aqi_city(city)
    meteo = await get_meteo_city(reading.city)
    fires = await get_fires()
    if gem_forecast is not None and _gemini_available:
        try:
            result = gem_forecast.forecast_aqi(reading, meteo, fires)  # type: ignore[attr-defined]
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except Exception:
            pass
    return rule_forecast(reading, meteo, fires)


@app.get("/api/crossborder", response_model=list[GeminiCrossBorderEvent])
async def api_crossborder():
    readings, fires, meteos = await asyncio.gather(get_aqi_all(), get_fires(), get_meteo_all())
    if gem_cross is not None and _gemini_available:
        try:
            result = gem_cross.detect_crossborder(readings, fires, meteos)  # type: ignore[attr-defined]
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except Exception:
            pass
    return rule_crossborder(readings, fires, meteos)


@app.get("/api/alerts", response_model=AlertMessage)
async def api_alerts(city: str = Query(...)):
    reading = await get_aqi_city(city)
    meteo = await get_meteo_city(reading.city)
    fires = await get_fires()
    analysis = rule_analysis(reading, meteo, fires)
    # Prefer Gemini analysis when available
    if gem_aqi is not None and _gemini_available:
        try:
            r = gem_aqi.analyze_aqi(reading, meteo)  # type: ignore[attr-defined]
            if asyncio.iscoroutine(r):
                r = await r
            analysis = r
        except Exception:
            pass
    events = rule_crossborder([reading], fires, [meteo])
    event = events[0] if events else None
    if gem_alerts is not None and _gemini_available:
        try:
            r = gem_alerts.generate_alert(analysis, event)  # type: ignore[attr-defined]
            if asyncio.iscoroutine(r):
                r = await r
            return r
        except Exception:
            pass
    return rule_alert(analysis, event)


@app.post("/api/analyze-photo", response_model=GeminiPhotoResult)
async def api_analyze_photo(
    city: str = Form(default="Delhi"),
    file: UploadFile = File(...),
):
    content = await file.read()
    if not content:
        return JSONResponse(status_code=400, content={"detail": "Empty file"})
    b64 = base64.b64encode(content).decode()
    photo = CitizenPhoto(city=city, image_base64=b64, uploaded_at=utcnow())
    if gem_photo is not None and _gemini_available:
        try:
            r = gem_photo.analyze_photo(photo)  # type: ignore[attr-defined]
            if asyncio.iscoroutine(r):
                r = await r
            return r
        except Exception:
            pass
    # Rule-based placeholder (valid schema, honest low confidence)
    kb = len(content) / 1024
    return GeminiPhotoResult(
        pollution_visible=True,
        pollution_type="haze/smoke (unverified — Gemini Vision pending)",
        estimated_aqi_category="Poor",
        visibility_km=round(max(0.5, 5.0 - min(kb / 500, 4.0)), 1),
        severity_score=6,
        likely_source="unknown — connect GEMINI_API_KEY for vision analysis",
        recommendation="Limit outdoor activity until verified analysis is available.",
        confidence=0.25,
    )


@app.exception_handler(KeyError)
async def key_error_handler(_, exc: KeyError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.get("/api/cities")
def api_cities():
    return BRICS_CITIES


@app.get("/api/meta")
def api_meta():
    return {
        "service": "BRICS Climate Intelligence Platform",
        "owner": "Sujal — data pipeline + backend",
        "gemini_live": bool(_gemini_available and any(m is not None for m in [gem_aqi, gem_forecast, gem_cross, gem_alerts, gem_photo])),
        "time": datetime.now().isoformat(),
    }


@app.get("/api/status")
def api_status():
    """Per-source resilience indicators (sidebar 'Data source indicators')."""
    oaq = _cache_state(openaq_mod, "OPENAQ_API_KEY")
    frs = _cache_state(firms_mod, "FIRMS_API_KEY")
    wqi = _cache_state(waqi_mod, "WAQI_TOKEN")
    sources = [
        {"source": "openaq", "layer": "Government AQI", "status": oaq[0], "detail": oaq[1]},
        {"source": "firms", "layer": "Satellite fires", "status": frs[0], "detail": frs[1]},
        {"source": "waqi", "layer": "Backup AQI", "status": wqi[0], "detail": wqi[1]},
        {"source": "meteo", "layer": "Wind/weather", "status": "live" if meteo_mod.load_cache() else "fallback",
         "detail": "Open-Meteo — no key required"},
        {"source": "sensors", "layer": "Citizen sensors", "status": "live" if sensors_mod and sensors_mod.load_cache() else "fallback",
         "detail": "Sensor.Community — no key required, snapshot present"},
    ]
    gem_status, gem_detail = _gemini_status()
    unknown = [s for s in sources if s["status"] == "unavailable"]
    overall = "degraded" if unknown or gem_status == "degraded" else "ok"
    return {
        "generated_at": datetime.now().isoformat(),
        "overall": overall,
        "gemini": {"status": gem_status, "detail": gem_detail},
        "sources": sources,
    }
