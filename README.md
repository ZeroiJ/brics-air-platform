# AeroBrics

**AI-Powered Federated Climate Action Platform**
Task 2 — Clean Air & Climate Resilience

> Government AQI stations report a city average. A citizen standing at the roadside
> sees something completely different. AeroBrics reads both — and works out where
> the pollution actually came from.

🔗 **Live prototype** → https://brics-air-frontend.onrender.com
🔗 **Backend API + OpenAPI docs** → https://brics-air-backend.onrender.com/docs

---

## The Problem

> Major Indian cities monitor macro-level air quality but consistently miss hyper-local
> pollution events — industrial emissions, large-scale agricultural burning, seasonal smog.
> The absence of real-time, granular data prevents coordinated climate action and directly
> threatens public health.

## The Challenge

> Build an AI-powered, federated climate action platform that combines citizen-sourced data
> (photos, local sensor readings) with satellite imagery and meteorological data. It should
> detect hidden pollution hotspots, forecast air quality spikes across major economic corridors,
> and alert relevant authorities for rapid intervention — designed for interoperability so
> Indian cities and states can share predictive models and coordinate resources.

---

## What we built

A working platform on **four independent data layers**, fused by Gemini into cross-border
attribution, spike forecasting, and authority alerts.

| Layer | Source | Auth | What it contributes |
|---|---|---|---|
| **L1 Government AQI** | OpenAQ v3, WAQI | key | Official station readings for 5 cities |
| **L2 Satellite** | NASA FIRMS VIIRS | key | Fire hotspots, fire radiative power (MW) |
| **L3 Meteorology** | Open-Meteo | none | Wind speed + direction, humidity, temperature |
| **L4 Citizen** | Sensor.Community, photo upload | none | Hyper-local sensors + eyewitness photo evidence |

Gemini then reasons **across all four at once** to produce five capabilities:

**1. Cross-border attribution** — the headline feature. Gemini sees fire positions, wind
vectors and AQI for every city simultaneously, and concludes *cause → effect*:
> Punjab / Amritsar crop burning → **Lahore**, E→W, **112 km**, severity **high**

**2. Hyper-local hotspot detection** — citizen sensor dots sit between government stations
on the same map, so sub-city events that a city average hides become visible.

**3. Spike forecasting** — 6h/24h AQI prediction that *cites its cause* (nearby fires +
wind transport time), not just a number.

**4. Citizen → authority chain** — upload a photo → GPS is read from the photo's own EXIF →
Gemini Vision scores it → the record is written to Postgres → routed to the named authority
(Delhi Pollution Control Committee, CETESB São Paulo, …).

**5. Federation / model exchange** — `BRICS-AIR-MODEL-EXCHANGE/1.0` publishes 5 versioned,
shareable contracts spanning 5 countries and 6 economic corridors. These are **declared wire
formats** (`trained: false`), not fitted weights — the honest way to satisfy "share
predictive models" without training models we didn't train.

---

## Architecture

```
┌────────────┐   only calls our API        ┌──────────────────────────────┐
│  Browser   │ ──────────────────────────▶ │  Streamlit dashboard         │
│ (judge)    │                             │  map · charts · alerts       │
└────────────┘                             └──────────────┬───────────────┘
                                                            │ HTTPS
                                                            ▼
                                            ┌───────────────────────────────┐
                                            │  FastAPI  (backend/main.py)  │
                                            │  · 16 endpoints, Pydantic     │
                                            │  · TTL cache + stale-while-   │
                                            │    revalidate                │
                                            │  · Gemini circuit breaker     │
                                            └───────┬───────────────┬───────┘
                    ┌───────────────────────────────┘               └──────────┐
                    ▼                                                          ▼
    ┌───────────────────────────────┐                        ┌──────────────────────────┐
    │  L1/L2/L3 pipeline modules    │                        │  L4 + store              │
    │  openaq · firms · meteo ·     │                        │  photo_meta (EXIF GPS)   │
    │  waqi · sensor_community      │                        │  store → Neon Postgres   │
    │  live → cache → fallback      │                        │  (text only, no image)   │
    └───────────────────────────────┘                        └──────────────────────────┘
                    │                                                          ▲
                    ▼                                                          │
            External data providers                        Gemini 3.6 Flash ─────┘
            OpenAQ · FIRMS · Open-Meteo                   5 modules, structured JSON
            WAQI · Sensor.Community                      circuit breaker + 6h cache
```

### Resilience design

Every layer is `live → cached snapshot → hardcoded fallback`, in that order. Nothing 500s
during a demo, and nothing is ever fabricated to fill a gap:

- `WAQI_TOKEN=demo` is **refused** — it returns Shanghai's AQI for every city on Earth
- Gemini quota exhaustion (HTTP 429) **fails fast** → circuit breaker opens → panels degrade
  to rule-based reasoning in ~1s instead of stalling 28s
- AI answers are cached **6h, keyed by city**, so a judge clicking between cities costs
  ~5 Gemini calls for the whole walkthrough

---

## How it's working

Deployed on Render (free tier), production smoke test **20/20**.

| | |
|---|---|
| **Data layers live** | 5/5 (openaq, FIRMS, WAQI, Open-Meteo, Sensor.Community) |
| **AI** | Gemini 3.6 Flash, 5/5 modules, structured JSON output |
| **Endpoints** | 16 (20 smoke checks incl. query variants) |
| **Persistence** | Neon Postgres (free tier) — survives deploys |
| **Cold dashboard load** | 27.8s → 2.6s (warm 0.03s) |
| **Cost** | $0 |

### Example live output

```
Delhi        AQI 467   PM2.5 451.0   ← real OpenAQ
Mumbai       AQI  68   PM2.5  20.4
São Paulo    AQI  72   PM2.5  22.0
Beijing      AQI  78   PM2.5  25.0
Johannesburg AQI 127   PM2.5  46.2

Cross-border:  Punjab/Amritsar (crop burning) → Lahore · E→W · 112.1 km · high
               Amazon basin (wildfire)       → São Paulo · NW→SE · 2435 km
Forecast:     467 → 6h 483 / 24h 501  (spike predicted, cause cited)
```

---

## API

| Endpoint | Returns |
|---|---|
| `GET /` | service info + dashboard link — **required**: Render probes `HEAD /` and kills the service on 404 |
| `GET /health` | `{"status":"ok"}` — UptimeRobot target |
| `GET /api/aqi[?city=]` | `AQIReading[]` |
| `GET /api/fires[?limit=]` | `FireHotspot[]` — NASA FIRMS VIIRS |
| `GET /api/meteo?city=` | `MeteoData` — Open-Meteo (no key) |
| `GET /api/sensors?country=` | `AQIReading[]` — citizen sensors |
| `GET /api/analysis?city=` | `GeminiAQIAnalysis` — cause attribution |
| `GET /api/forecast?city=` | `GeminiForecast` — 6h/24h spike |
| `GET /api/crossborder` | `GeminiCrossBorderEvent[]` |
| `GET /api/alerts?city=` | `AlertMessage` — Hindi / Portuguese / English |
| `POST /api/analyze-photo` | `PhotoAnalysisResult` + report id, GPS, routed authority |
| `GET /api/reports[?city=&limit=]` | citizen evidence records |
| `GET /api/models[/{id}]` | federation model-exchange registry |
| `GET /api/cities`, `/api/meta`, `/api/status` | metadata + per-source live/cached/fallback |

Cities: **Delhi, Mumbai, São Paulo, Beijing, Johannesburg**

---

## Configuration

| Key | Where to get it | Needed for |
|---|---|---|
| `OPENAQ_API_KEY` | explore.openaq.org → register | Government AQI |
| `FIRMS_API_KEY` | firms.modaps.eosdis.nasa.gov/api/map_key (email) | Fire hotspots |
| `WAQI_TOKEN` | aqicn.org/data-platform/token | Backup AQI |
| `GEMINI_API_KEY` | aistudio.google.com → Get API Key | AI reasoning |
| `DATABASE_URL` | Neon console → connection string | Citizen report storage |
| `BACKEND_URL` | deployed frontend URL | frontend → backend |

`.env` is gitignored. **Share keys out-of-band, never in git.** If `DATABASE_URL` is unset,
citizen reports fall back to a local JSON file.

```bash
cp .env.example .env      # fill keys
pip install -r requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000
streamlit run frontend/app.py
```

---

## Current limitations

Stated plainly, because a judge will ask:

1. **Delivery is recorded, not sent.** A routed report carries `delivery_status: "recorded"`
   — the routing decision is logged and the authority is named. No SMTP or Cloud Function
   actually messages CPCB. Those require a paid (Blaze) plan, and we would rather say so
   than fake a sent email.
2. **Image bytes are not stored.** Per the team's decision, a photo upload persists only its
   *record* — coordinates, citizen description, Gemini verdict, SHA-256, byte size. This keeps
   storage ~1 KB/report, but the original image is not retained for later re-examination.
3. **Photo geolocation needs EXIF.** GPS comes from the phone's embedded coordinates. Desktop
   screenshots and re-encoded images have none, and fall back to a city centroid — labelled
   `location_source: "city"` so a guess is never presented as a citizen's real position.
4. **Free-tier Gemini quota is ~20 generations/day per account.** The circuit breaker and
   6h city-keyed cache make this survivable, but sustained heavy use would show rule-based
   reasoning instead of live AI prose. Quota resets midnight Pacific.
5. **City granularity, not state.** The challenge mentions Indian *cities and states*; we
   operate per-city. No district or state-level aggregation is implemented.
6. **Federation is a contract, not a live mesh.** `trained: false` on every card. We publish
   the interoperable wire format and prove it runs across 5 countries — we do not run
   multiple connected nodes exchanging models.
7. **Render free tier sleeps after ~15 min idle.** First load after sleep takes ~33s. UptimeRobot
   (5-minute `/health` ping) mitigates this.
8. **English + Hindi + Portuguese only.** Alert languages are fixed to the PS-specified three.

---

## Structure

```
backend/
  models.py            # ALL Pydantic schemas (the contract every module uses)
  main.py              # FastAPI app — 16 endpoints
  federation.py        # model-exchange registry (declared contracts)
  store.py             # citizen reports → Neon Postgres, local JSON fallback
  photo_meta.py        # EXIF GPS extraction (never raises)
  database.py          # legacy SQLite (unused — Render FS is ephemeral)
  pipeline/            # openaq, firms, meteo, waqi, sensor_community
  gemini/              # aqi_analysis, forecast, crossborder, alerts, photo_analysis
  cache/               # committed demo snapshots
frontend/app.py        # Streamlit dashboard, 8 themes
scripts/               # smoke_test.py, refresh_cache.py
docs/                  # DEPLOY.md, PS_COVERAGE.md
```

## Team

- **Sujal** — data pipeline, FastAPI backend, deployment
- **Sarthak** — Gemini AI modules
- **Anoushka** — Streamlit frontend

`changelog.md` (work log) · `work-division.md` (plan) · `docs/PS_COVERAGE.md` (requirement → endpoint → UI matrix)

## Verification

```bash
python scripts/smoke_test.py                                          # local
python scripts/smoke_test.py --base-url https://brics-air-backend.onrender.com   # deployed
python verify_frontend.py                                              # 8 themes, 0 exceptions
```

Deploy: `render.yaml` (Blueprint) + `docs/DEPLOY.md`.
