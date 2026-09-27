# PS Coverage Audit — BRICS Sustainability Challenge
**Audited: 27 Sep 2026 · against the official problem/challenge statement**

| # | PS requirement | Data layer / endpoint | UI (frontend/app.py) | Status |
|---|---|---|---|---|
| 1 | **Citizen-sourced data — photos** | `POST /api/analyze-photo` (Gemini Vision) | Citizen Photo Intake card + file uploader + graded result (type, visibility, severity 1–10, advice) | ✅ |
| 2 | **Citizen-sourced data — local sensors** | `GET /api/sensors?country=` (Sensor.Community) | Hyper-Local Citizen Sensors card (count, peak PM2.5, top-8 table) + grey sensor dots on the map | ✅ |
| 3 | **National satellite imagery** | `GET /api/fires` (NASA FIRMS VIIRS) | Red fire markers on Folium map (radius/opacity scaled by FRP), layer control | ✅ |
| 4 | **Meteorological data** | `GET /api/meteo?city=` (Open-Meteo) | Blue wind-vector arrow at selected city (direction corrected from FROM → transport TO) | ✅ |
| 5 | **Detect hidden hyper-local hotspots** | sensors + fires + AQI | Sensor dots + fire clusters + cross-border detection cards | ✅ |
| 6 | **Forecast AQI spikes across economic corridors** | `GET /api/forecast?city=`, `GET /api/crossborder` | 24h Outlook card (6h/24h + spike cause) + Transboundary Event cards (source→affected, km, severity, evidence) | ✅ |
| 7 | **Alert relevant authorities** | `GET /api/alerts?city=` | Authority Alert card (target authority + urgency) + Hindi / Portuguese / English message columns | ✅ |
| 8 | **Federated / interoperable model sharing** | `GET /api/models`, `GET /api/models/{id}` | Federation / Model Exchange card (5 contracts, 5 countries, 6 corridors) | ✅ |

**8/8 covered.**

## How requirement 8 is met (without overclaiming)

PS: *"designed for interoperability so BRICS nations can share predictive models and
coordinate resources."*

`backend/federation.py` publishes a **model-exchange registry** — a `BRICS-AIR-MODEL-EXCHANGE/1.0`
protocol node offering 5 versioned contracts. Each card declares the wire format a peer BRICS
node would consume: `id, version, module, kind, task, input_layers, input_schema, output_schema,
corridors, countries, transport, license`.

**This is a contract registry, not a model zoo, and the API says so explicitly.** `work-division.md`
lists *"train custom ML models"* as an anti-pattern, so every card carries `trained: false` and
names the real in-repo module implementing it. Nothing is fabricated:

- every `output_schema` resolves to an actual Pydantic class in `backend/models.py`
  (verified — 5/5, 0 broken references)
- corridors are the ones the cross-border detector actually evaluates
  (Indo-Gangetic IN→PK, Amazon Basin, Beijing-Tianjin, Mpumalanga)
- countries are the five in `BRICS_CITIES`

The claim is therefore verifiable: *we publish the interoperable interface and prove it already
runs across five countries*, rather than dressing up a stub as fitted weights.

Both endpoints are **pure metadata reads** — no network calls, no Gemini quota — so the
federation card cannot fail or stall during a demo.

## Demo walkthrough (what judges will see)

1. Dashboard loads → 3 live cards (AQI / Risk / 24h Outlook) + sidebar source indicators (live/cached/fallback)
2. Dark folium map: red fire clusters, colored AQI city markers, wind arrow, grey hyper-local sensor dots
3. Cross-border event card: e.g. Punjab → Delhi / Amazon → São Paulo (source, cause, direction, km, evidence)
4. Plotly chart: 5-city PM2.5 vs red dashed WHO 15 µg/m³ line
5. Authority alert: target + urgency + 3 languages
6. Upload smog photo → Gemini Vision severity card
7. Switch city (sidebar) → whole board re-scopes (cache 60s)
8. Federation / Model Exchange card → 5 shareable contracts, 5 countries, 6 corridors, `GET /api/models`
