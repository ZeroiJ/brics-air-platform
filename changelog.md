# Changelog

## Sujal — Data Pipeline + Backend

### 18 Sep 2026 — Steps 0–4 complete, all endpoints verified

**Step 0 — Repo hygiene**
- `.gitignore` — secrets (`.env`), venv, `*.db`, OS cruft. `backend/cache/*.json` intentionally TRACKED (cold-start demo fallback).
- `requirements.txt` — fixed from spec: dropped `sqlite3` (stdlib, unpipable), added `google-genai` (Sarthak), `python-multipart` (photo upload). Pinned minimums.
- `.env.example` — `OPENAQ_API_KEY / FIRMS_API_KEY / WAQI_TOKEN / GEMINI_API_KEY / BACKEND_URL`. No real `.env` committed.

**Step 1 — `backend/models.py` (contract for Sarthak + Anoushka)**
- All 9 schemas exactly as specced: `AQIReading`, `FireHotspot`, `MeteoData`, `CitizenPhoto`, `GeminiAQIAnalysis`, `GeminiForecast`, `GeminiCrossBorderEvent`, `GeminiPhotoResult`, `AlertMessage`.
- Added `BRICS_CITIES` + `CITY_LOOKUP`/`lookup_city()` single source of truth (Delhi, Mumbai, São Paulo, Beijing, Johannesburg with lat/lng). Pydantic v2, `utcnow()` default for photo timestamps.

**Step 2 — Pipeline (5 modules, each: live fetch + `save/load_cache` + `fallback()`)**
- `pipeline/openaq.py` (httpx, async) — v3 locations→latest, `X-API-Key` header, PM2.5→US-EPA-AQI conversion (`pm25_to_aqi`). No key → fallback (Delhi 287, Mumbai 132, São Paulo 68, Beijing 156, JHB 54).
- `pipeline/meteo.py` (httpx, async, no key) — Open-Meteo `current=` query, `deg_to_label()` cardinal conversion. LIVE and working (verified 18 Sep).
- `pipeline/firms.py` (requests, sync) — VIIRS_SNPP_NRT × 2 bboxes (S.Asia 60,5,100,40 + S.America −80,−40,−30,10), CSV parse, FRP-sorted cap 300. Fallback: 6 Punjab + 4 Amazon + 2 Mpumalanga hotspots.
- `pipeline/sensor_community.py` (requests, sync, no key) — `filter/country={IN,BR,CN,ZA}`, P1/P2 parse, ≤6h freshness, 50/country cap, `source="sensor_community"`. LIVE and working (41 rows fetched 18 Sep).
- `pipeline/waqi.py` (httpx, async) — backup feed per city slug, used only when OpenAQ fails; fallback mirrors OpenAQ with `source="waqi"`.

**Step 3 — `backend/main.py` (FastAPI, port 8000)**
- CORS open, `KeyError→404` handler, `GET /health`, `GET /api/cities`, `GET /api/meta`.
- Data: `GET /api/aqi[?city]`, `GET /api/fires[?limit]`, `GET /api/meteo[?city]`, `GET /api/sensors[?country]`.
- AI: `GET /api/analysis?city`, `GET /api/forecast?city`, `GET /api/crossborder`, `GET /api/alerts?city`, `POST /api/analyze-photo` (multipart `file` + `city` form field).
- Resilience: every data route is live→cache→fallback, never 500s. Gemini routes try Sarthak's `backend.gemini.*` when `GEMINI_API_KEY` is set, else deterministic rule-based fallbacks (`rule_analysis/forecast/crossborder/alert`) returning valid schemas — frontend unblocked today. Verified: `uvicorn backend.main:app` boots; TestClient 13/13 routes 200; unknown city 404; photo POST 200.

**Step 4 — Cache prefetch (`backend/cache/*.json`, committed)**
- `openaq.json` 5 rows (fallback — no key yet), `meteo.json` 5 rows (live), `firms.json` 12 rows (fallback), `sensors.json` 41 rows (live citizen sensors), `waqi.json` 5 rows (fallback mirror).

**`backend/database.py` (SQLite)**
- `brics_air.db` (gitignored), WAL mode, tables `aqi_readings/meteo/fires`; `init_db()`, `save_aqi_batch()`, `latest_aqi()`. Writes best-effort. Verified 5-row write.

**Handoff**
- Sarthak: `from backend.models import ...`; implement `backend/gemini/{aqi_analysis,forecast,crossborder,alerts,photo_analysis}.py` with functions `analyze_aqi / forecast_aqi / detect_crossborder / generate_alert / analyze_photo` — `main.py` auto-picks them up when `GEMINI_API_KEY` is set, no backend changes needed.
- Anoushka: base URL `http://localhost:8000`; start with `GET /api/aqi` + `GET /api/fires` (live now). Query params: `?city=Delhi`, `?country=IN`, `?limit=300`.

**Still pending (Sujal)**
- Real keys for OpenAQ/WAQI/Gemini over WhatsApp → re-run prefetch to replace fallback rows.
- Render deploy + UptimeRobot (Day 26 Sep per plan).

### 18 Sep 2026 — FIRMS key live
- `FIRMS_API_KEY` saved to local `.env` (gitignored, not committed).
- Verified live: South Asia bbox 505 hotspots, South America bbox 11,189 hotspots; `fetch_fires(limit=300)` returns FRP-sorted VIIRS rows.
- `backend/cache/firms.json` refreshed from 12-row fallback to 300-row live snapshot (56K). `GET /api/fires` serves live data.
- Still missing: `OPENAQ_API_KEY`, `WAQI_TOKEN`, `GEMINI_API_KEY` (OpenAQ/WAQI fallbacks active, Gemini routes on rule-based stand-ins).

### 18 Sep 2026 — README added + pushed
- `README.md`: quickstart, endpoint table, key sources, structure, team. Committed + pushed to `origin/main`.

### 19 Sep 2026 — Day 2: demo readiness + team tooling
- `rule_crossborder()` in `main.py`: added **India → Pakistan corridor** — Punjab/Amritsar border-belt fires + easterly flow now emit a Lahore cross-border event (Indo-Gangetic Plain, demo step 3). Existing Punjab→Delhi + Amazon→São Paulo events unchanged.
- `scripts/refresh_cache.py`: one command to re-fetch all data sources. Skips sources whose key is missing (never clobbers committed cache), always refreshes no-key sources (meteo, sensors).
- `scripts/smoke_test.py`: 15 checks on every endpoint + shapes + 404 case (in-process `TestClient`); `--base-url` flag for testing the deployed Render backend later.
- Status: OpenAQ + WAQI keys still pending (user couldn't reach the signup/token pages); both modules sit in fallback mode — FIRMS, meteo, sensors are LIVE so nothing blocks Sarthak/Anoushka.

### 22 Sep 2026 — PR review + merge (Sujal)
- Reviewed Sarthak's `sarthak/gemini-modules` (fork: `nglfrsarthak`) + Anoushka's `anoushka/frontend-reference` (fork: `Glizussy`), both PR-ready on forks.
- **Merge 1 — Sarthak Gemini:** `backend/gemini/_common.py` (shared lazy client, 180s HTTP timeout, tenacity retry via `GEMINI_RETRIES`) + all 5 modules (`aqi_analysis`, `forecast`, `crossborder`, `alerts`, `photo_analysis`). Entry-point signatures match my `main.py` contract exactly (`analyze_aqi`, `forecast_aqi`, `detect_crossborder`, `generate_alert`, `analyze_photo`). Models `gemini-3.6-flash` (2.5-flash retired) with per-module env overrides; ground truth (city/aqi/authority) forced from inputs, not the LLM. Verified: all 5 import cleanly, each raises `RuntimeError` without a key — `main.py`'s try/except fallback chain catches all → no 500s, smoke test holds. `aqi_analysis` already live end-to-end on Sarthak's key (`/api/analysis?city=Delhi` → real Gemini output); `forecast` live too (Delhi 287 → 6h 322 / 24h 295, spike warning).
- **Merge 2 — Anoushka frontend:** `.streamlit/config.toml` (dark theme, headless, minimal toolbar) + `frontend/app.py` (735 lines — 8 themes, city selector, AQI/risk/24h-forecast cards, folium+plotly-free custom panels, offline mock mode, zero emojis, calls ONLY my endpoints via `_get` with 3s/10s timeouts + graceful `None`) + `verify_frontend.py` (headless theme verification harness, 8 themes × 12 CSS vars).
- **Integration state:** backend 14/14 smoke pass; frontend structure verified; Gemini key rotation rule set — each dev uses own key locally, dedicated key for Render deploy (free tier ≈ 20 calls/day/key, demo run ≈ 4 calls).
- OpenAQ + WAQI still keyless (fallback). Pushed to `origin/main`.

### 22 Sep 2026 — Status endpoint, Render blueprint + deploy runbook (Sujal)
- `GET /api/status` (new): per-source resilience indicators (`live` | `cached` | `fallback`) + Gemini state + overall health. Returns: openaq/firms/waqi (key-gated), meteo/sensors (no-key always-live), Gemini module count.
  - In this sandbox: FIRMS `live`, meteo/sensors `live`, openaq/waqi `cached`, gemini `fallback` → `overall: ok`.
  - Smoke test updated: 15/15 pass.
- `render.yaml` (Render Blueprint): two services (`brics-air-backend` + `brics-air-frontend`), free tier, auto-deploy from `main`, `BACKEND_URL` auto-wired to backend internal URL via `hostport`.
- `docs/DEPLOY.md`: full deploy runbook (render.com Blueprint → env vars → UptimeRobot ping at `/health` every 5 min → cold-start warm-up on demo day → rollback/redeploy flow + env var reference table).
- `README.md` updated: `/api/status` row in API table, deploy docs reference.
Changelog updated.

### 22 Sep 2026 — LIVE on Render (Sujal, deploy moved up from Sep 26)
- Blueprint deploy from `render.yaml`: pulled into repo `ZeroiJ/brics-air-platform` → Render auto-created both services.
- **`brics-air-backend`** → `https://brics-air-backend.onrender.com` — `/health` 200, responding in ~1.5s cold.
- **`brics-air-frontend`** → `https://brics-air-frontend.onrender.com` — `/_stcore/health` 200.
- Config hardened pre-deploy: bind `$PORT`, pin `PYTHON_VERSION 3.12.10`, `GEMINI_RETRIES 5`, health checks at `/health` + `/_stcore/health`, frontend `BACKEND_URL` auto-wired via `hostport`.
- Manual backend-only path documented in `docs/DEPLOY.md` (Option B).
- TODO next: UptimeRobot 5-min ping on `/health` (keeps free tier hot), frontend env vars confirmed in dashboard, harden for demo day (auto-deploy off).
- **Production sweep: 15/15 PASS** against `https://brics-air-backend.onrender.com` (TestClient → real network hits). Live state on Render: FIRMS `live`, meteo `live`, sensors `live`, openaq `cached`, waqi `cached`, gemini `fallback` (key not set on Render yet), `overall: ok`.
- **Key action for Sujal:** set `GEMINI_API_KEY` (dedicated deploy key) in the backend's Render Environment tab → Gemini goes live on prod. OpenAQ/WAQI keys optional (fallback fine).

## Sarthak — Gemini AI

### 20 Sep 2026 — All 5 Gemini modules written, Module 1 live end-to-end
- `backend/gemini/_common.py`: shared lazy client, tenacity retry (3x, exp backoff on API errors), structured-output extraction (`response.parsed` → JSON), `haversine_km`.
- `backend/gemini/aqi_analysis.py` — **LIVE through `/api/analysis?city=Delhi`** (`gemini_live=true`). Uses `gemini-3.6-flash` (2.5-flash retired for new accounts; API drove the upgrade). Verified output: blood-risk vocabulary pinned to Indian AQI categories; ground-truth `city` forced from input (Gemini appended ", India" once).
- `backend/gemini/forecast.py`: 500-km fire window + upwind/downwind bearing math (unit-checked: NW fire + NW wind = upwind), 6h/24h AQI + spike cause. Live-tested pre-quota: Delhi 287 → 322/295, spike warning.
- `backend/gemini/crossborder.py`: compact 5°-grid fire-cluster prompt, Pro→flash fallback (Pro models have **zero free-tier quota** — `limit: 0`), de-dup + only events for monitored cities. Evidence-based: returned 0 events when live Delhi wind (NE 3.7 km/h) doesn't support Punjab transport; detects events when wind does.
- `backend/gemini/alerts.py`: ONE call → Hindi + Portuguese + English + authority (authority forced from team mapping) + urgency.
- `backend/gemini/photo_analysis.py`: magic-byte MIME sniffing (JPEG/PNG/WebP/GIF), Gemini Vision structured analysis.
- **Quota reality:** free-tier = 20 generations/day for `gemini-3.6-flash` per key. Testing exhausted it same-day. Plan: each teammate uses their own key for local dev; dedicated key for the deployed backend; demo run ≈ 4 calls. Sujal's fallback chain verified: smoke test 14/14 even with quota exhausted.
- Smoke test 14/14 with key set; pushed as branch `sarthak/gemini-modules` on Sarthak's fork (PR-ready, nothing pushed to upstream).
