# PS Coverage Audit — BRICS Sustainability Challenge
**Audited: 23 Sep 2026 · against the official problem/challenge statement**

| # | PS requirement | Data layer / endpoint | UI (frontend/app.py) | Status |
|---|---|---|---|---|
| 1 | **Citizen-sourced data — photos** | `POST /api/analyze-photo` (Gemini Vision) | Citizen Photo Intake card + file uploader + graded result (type, visibility, severity 1–10, advice) | ✅ |
| 2 | **Citizen-sourced data — local sensors** | `GET /api/sensors?country=` (Sensor.Community) | Hyper-Local Citizen Sensors card (count, peak PM2.5, top-8 table) + grey sensor dots on the map | ✅ |
| 3 | **National satellite imagery** | `GET /api/fires` (NASA FIRMS VIIRS) | Red fire markers on Folium map (radius/opacity scaled by FRP), layer control | ✅ |
| 4 | **Meteorological data** | `GET /api/meteo?city=` (Open-Meteo) | Blue wind-vector arrow at selected city (direction corrected from FROM → transport TO) | ✅ |
| 5 | **Detect hidden hyper-local hotspots** | sensors + fires + AQI | Sensor dots + fire clusters + cross-border detection cards | ✅ |
| 6 | **Forecast AQI spikes across economic corridors** | `GET /api/forecast?city=`, `GET /api/crossborder` | 24h Outlook card (6h/24h + spike cause) + Transboundary Event cards (source→affected, km, severity, evidence) | ✅ |
| 7 | **Alert relevant authorities** | `GET /api/alerts?city=` | Authority Alert card (target authority + urgency) + Hindi / Portuguese / English message columns | ✅ |
| 8 | **Federalated / interoperable model sharing** | — | — | ❌ **GAP** (see below) |

## The one remaining gap: federation

PS: *"designed for interoperability so BRICS nations can share predictive models and coordinate resources."*

Today the platform is interoperable at the **data** level (BRICS cities, ISO-ish fields, one API), but nothing
represents the **model-sharing** contract. Minimal honest fix (≈1 day):

- `GET /api/models` — registry of shareable predictive model cards:
  `id, name, version, task, inputs[], output_schema, corridors[], countries[], eval metrics, license, endpoint`
- Models registered today: `delhi-smoke-transport-v1`, `sp-sa-smoke-v1`, `forecast-6h-24h-v1`
- One "FEDERATION / MODEL EXCHANGE" card in the UI: catalog table + "shareable across BRICS nodes" note
- No custom training (anti-pattern) — these are declared contracts for the Gemini reasoning modules
  + rule-based forecaster, versioned like any shared artifact.

## Demo walkthrough (what judges will see)

1. Dashboard loads → 3 live cards (AQI / Risk / 24h Outlook) + sidebar source indicators (live/cached/fallback)
2. Dark folium map: red fire clusters, colored AQI city markers, wind arrow, grey hyper-local sensor dots
3. Cross-border event card: e.g. Punjab → Delhi / Amazon → São Paulo (source, cause, direction, km, evidence)
4. Plotly chart: 5-city PM2.5 vs red dashed WHO 15 µg/m³ line
5. Authority alert: target + urgency + 3 languages
6. Upload smog photo → Gemini Vision severity card
7. Switch city (sidebar) → whole board re-scopes (cache 60s)
