"""Sarthak — Module 2: 24h AQI spike forecasting.

Input:  AQIReading (current) + MeteoData + list[FireHotspot] (full, from Sujal)
Output: GeminiForecast

Gemini is asked to predict AQI at +6h and +24h from:
  - current AQI + PM2.5
  - wind speed/direction (transport speed → arrival time)
  - nearby active fires (proximity, intensity/FRP, upwind vs downwind)
  - typical diurnal patterns

Contract with Sujal's backend (backend/main.py):
    result = gem_forecast.forecast_aqi(reading, meteo, fires)
Raises on failure -> main.py falls back to rule_forecast(). Never 500.
"""
from __future__ import annotations

import os

from backend.gemini._common import gemini_retry, get_client, haversine_km, to_model
from backend.models import AQIReading, FireHotspot, GeminiForecast, MeteoData

MODEL = os.getenv("GEMINI_FORECAST_MODEL", "gemini-3.6-flash")
NEARBY_KM = 500.0


def _nearby_fires(reading: AQIReading, fires: list[FireHotspot]) -> list[FireHotspot]:
    """Fires within NEARBY_KM of the city, sorted by distance."""
    scored = sorted(
        ((haversine_km(reading.lat, reading.lng, f.lat, f.lng), f) for f in fires),
        key=lambda t: t[0],
    )
    return [f for d, f in scored if d <= NEARBY_KM]


def _is_upwind(reading: AQIReading, meteo: MeteoData, fire: FireHotspot) -> bool:
    """True if the wind blows FROM the fire's direction toward the city.

    A fire is upwind when it lies in the sector the wind comes FROM:
    e.g. wind from NW (315°) + fires NW of the city -> smoke transported
    toward the city.
    """
    import math

    # Compass bearing from the CITY toward the FIRE (0=N, 90=E, ...)
    dy = fire.lng - reading.lng
    dx = fire.lat - reading.lat
    bearing = (math.degrees(math.atan2(dy, dx)) + 360) % 360
    # wind_direction_deg is the direction the wind comes FROM. Fires within
    # +/-90° of that upwind sector blow smoke toward the city.
    diff = abs((bearing - meteo.wind_direction_deg + 180) % 360 - 180)
    return diff <= 90


@gemini_retry
def _call_gemini(
    reading: AQIReading, meteo: MeteoData, nearby: list[FireHotspot]
) -> GeminiForecast:
    client = get_client()
    nearest = nearby[0] if nearby else None
    min_dist = (
        round(haversine_km(reading.lat, reading.lng, nearest.lat, nearest.lng))
        if nearest
        else 0
    )
    max_frp = max((f.frp for f in nearby), default=0.0)
    upwind = (
        _is_upwind(reading, meteo, nearest) if nearest else False
    )
    wind_label = meteo.wind_direction_label

    prompt = f"""Predict the air quality forecast for {reading.city}.

Current conditions:
- AQI: {reading.aqi} (PM2.5 {reading.pm25} µg/m³, PM10 {reading.pm10} µg/m³)
- Wind: {meteo.wind_speed_kmh} km/h from {wind_label} ({round(meteo.wind_direction_deg)}°) 
- Temperature: {meteo.temperature_c}°C, humidity {meteo.humidity_pct}%
- Active fires within 500 km: {len(nearby)}
- Nearest fire: {min_dist} km away, {'UPWIND (smoke blowing toward city)' if upwind else 'downwind (smoke blowing away)'}
- Max fire radiative power among nearby fires: {round(max_frp, 1)} MW

Forecast AQI for 6 hours and 24 hours from now. Consider:
1. Transport time: wind {meteo.wind_speed_kmh} km/h carries smoke; a fire at {min_dist}
   km arrives in roughly {round(min_dist / max(meteo.wind_speed_kmh, 1) * 60)} minutes.
2. Fire intensity (FRP) and whether fires are upwind.
3. Typical diurnal AQI patterns (evening/night stagnation raises PM2.5).
4. Spike warning: TRUE only if a meaningful rise (>+30 AQI or crossing 200) is expected.

Return structured JSON only. Values must be integers for AQI fields."""
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={
            "system_instruction": (
                "You are a meteorological and air-quality forecaster for BRICS "
                "cities. AQI uses the US EPA scale. Be quantitative, be "
                "conservative about spike_warning, and return structured JSON."
            ),
            "response_mime_type": "application/json",
            "response_schema": GeminiForecast.model_json_schema(),
            "temperature": 0.2,
        },
    )
    return to_model(response, GeminiForecast)


def forecast_aqi(
    reading: AQIReading, meteo: MeteoData, fires: list[FireHotspot]
) -> GeminiForecast:
    """Gemini 6h/24h AQI forecast (Sujal's contract). Raises on failure."""
    nearby = _nearby_fires(reading, fires)
    result = _call_gemini(reading, meteo, nearby)
    # Ground truth from inputs, not the LLM.
    result.city = reading.city
    result.current_aqi = reading.aqi
    return result