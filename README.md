# BRICS Climate Intelligence Platform

**Track 2 — Clean Air & Climate Resilience (BRICS Theme: Sustainability)**

AI-powered, federated climate action platform. Combines citizen data (photos, local sensors)
with satellite fire detection + meteorological data to find hidden hotspots, forecast AQI spikes
across BRICS corridors, and alert authorities — built so BRICS nations can share models.

## Status (18 Sep 2026)

- ✅ Sujal: backend pipeline + FastAPI backbone live (FIRMS + meteo + citizen sensors live, OpenAQ/WAQI on fallback until keys arrive)
- ⏳ Sarthak: Gemini modules (`backend/gemini/`) — rule-based stand-ins active so frontend is unblocked
- ⏳ Anoushka: Streamlit dashboard (`frontend/`)

## Quickstart (backend)

```bash
cp .env.example .env   # fill keys, never commit .env
pip install -r requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000
# docs: http://localhost:8000/docs
```

## API

| Endpoint | Returns |
|---|---|
| `GET /health` | `{"status":"ok"}` |
| `GET /api/aqi[?city=Delhi]` | `AQIReading[]` — OpenAQ, WAQI fallback |
| `GET /api/fires[?limit=300]` | `FireHotspot[]` — NASA FIRMS VIIRS |
| `GET /api/meteo[?city=Delhi]` | `MeteoData` — Open-Meteo (no key) |
| `GET /api/sensors[?country=IN]` | `AQIReading[]` — Sensor.Community citizens |
| `GET /api/analysis?city=Delhi` | `GeminiAQIAnalysis` |
| `GET /api/forecast?city=Delhi` | `GeminiForecast` |
| `GET /api/crossborder` | `GeminiCrossBorderEvent[]` |
| `GET /api/alerts?city=Delhi` | `AlertMessage` (Hindi/Portuguese/English) |
| `POST /api/analyze-photo` | `GeminiPhotoResult` (multipart `file` + `city`) |
| `GET /api/cities`, `GET /api/meta` | metadata |
| `GET /api/status` | per-source data indicators (live/cached/fallback) + Gemini state |

Cities: Delhi, Mumbai, São Paulo, Beijing, Johannesburg.
Every data route is live → `backend/cache/*.json` → hardcoded fallback. Never 500s during demo.

## Env keys

| Key | Where | Needed for |
|---|---|---|
| `OPENAQ_API_KEY` | explore.openaq.org → register → account page | Gov AQI |
| `FIRMS_API_KEY` | firms.modaps.eosdis.nasa.gov/api/map_key (email) | Fire hotspots |
| `WAQI_TOKEN` | aqicn.org/data-platform/token | Backup AQI |
| `GEMINI_API_KEY` | aistudio.google.com → Get API Key | AI reasoning |

Share keys over WhatsApp, never in git. On Render: dashboard → Environment tab.

## Structure

```
backend/
  models.py            # ALL Pydantic schemas (contract)
  main.py              # FastAPI app
  pipeline/            # openaq, firms, meteo, sensor_community, waqi
  gemini/              # Sarthak (stubs wired, optional until key lands)
  database.py          # SQLite (gitignored db)
  cache/               # committed demo snapshots
frontend/              # Anoushka — Streamlit
```

## Team

- Sujal — data pipeline + backend
- Sarthak — Gemini AI
- Anoushka — frontend

See `work-division.md` (plan) + `changelog.md` (progress).

## Scripts

```bash
python scripts/refresh_cache.py            # refresh backend/cache/*.json
python scripts/smoke_test.py               # verify all endpoints locally
python scripts/smoke_test.py --base-url https://backend.onrender.com  # after deploy
```

Deploy: `render.yaml` (Blueprint) + `docs/DEPLOY.md` (Render + UptimeRobot runbook).
Everything degrades gracefully with zero keys — fallback is a feature.
