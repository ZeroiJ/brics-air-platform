# Deploy Runbook — Render.com + UptimeRobot (Sujal, Day 26 Sep)

Both services on Render free tier. Total cost: **$0**.

---

## 0. Before you start (5 min)

- [ ] Keys ready: `OPENAQ_API_KEY`, `FIRMS_API_KEY`, `WAQI_TOKEN`, `GEMINI_API_KEY`
  - (FIRMS key you have. OpenAQ/WAQI pending; **Gemini must be a dedicated key**, not your dev key —
    free tier is ~20 calls/day and the demo run uses ~4)
- [ ] Repo pushed to `github.com/ZeroiJ/brics-air-platform` (**main branch**, latest merge of
      Sarthak + Anoushka + your status endpoint)
- [ ] Created free account at `render.com`

## 1. Deploy (pick one)

### Option A — Blueprint (both services, recommended)

1. Render dashboard → **New → Blueprint**
2. Select `ZeroiJ/brics-air-platform` → Render reads `render.yaml`
3. It prompts for secrets (fill when prompted):
   - `OPENAQ_API_KEY` = *(blank or paste when available)*
   - `FIRMS_API_KEY` = `010ca454ff64927fa3029df0fe5ad9be` *(your key)*
   - `WAQI_TOKEN` = *(blank or paste when available)*
   - `GEMINI_API_KEY` = *(dedicated deploy key — see section 0)*
4. **Apply** → both services build + deploy

### Option B — Backend only (manual, fast)

1. Render dashboard → **New → Web Service**
2. Connect GitHub → pick `ZeroiJ/brics-air-platform`
3. Fill these exact values:
   | Field | Value |
   |---|---|
   | Name | `brics-air-backend` |
   | Region | Singapore / Frankfurt / Ohio (pick nearest) |
   | Runtime | Python |
   | Branch | `main` |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` |
   | Plan | Free |
4. **Advanced → Health Check Path** → `/health`
5. **Environment** tab → add these key-value pairs:
   ```
   PYTHON_VERSION = 3.12.10
   FIRMS_API_KEY = 010ca454ff64927fa3029df0fe5ad9be
   GEMINI_API_KEY = <your dedicated deploy key>
   OPENAQ_API_KEY = <blank for now>
   WAQI_TOKEN     = <blank for now>
   ```
6. **Create Web Service** → wait ~60s for build

## 2. Verify

Backend (once deployed):
```bash
curl https://<backend>.onrender.com/health          # {"status":"ok"}
curl https://<backend>.onrender.com/api/status      # per-source: live/cached/fallback
curl "https://<backend>.onrender.com/api/analysis?city=Delhi"
```

Frontend: open `https://<frontend>.onrender.com` — dashboard must show data.
A deployed check that covers everything:
```bash
python scripts/smoke_test.py --base-url https://<backend>.onrender.com   # expect 15/15
```

> **Port note:** Render injects the `PORT` env var — always bind with `$PORT`,
> never a hardcoded `8000`/`8501`. Locally you keep using `--port 8000`.

## 3. UptimeRobot (keep free tier awake)

Render free instances spin down after ~15 min idle. UptimeRobot pings keep it hot.

1. Sign up at `uptimerobot.com` (free)
2. **Add New Monitor**:
   - Type: HTTP(s)
   - URL: `https://<backend>.onrender.com/health`
   - Interval: **5 minutes** (min free = 5m)
   - Alert contacts: your email/WhatsApp
3. Repeat for the frontend: `https://<frontend>.onrender.com` (interval 30m is fine)
4. Optional: set Monitor Type = Keyword + "ok" so it only alerts if `/health` is unhealthy

## 4. On demo day (30 Sep)

- Free tier cold-start ~30-60s on first hit — **warm both apps 10 min before judging** (curl health)
- Demo run costs ~4 Gemini calls — the dedicated deploy key holds ~20/day, enough for 2 full run-throughs
- If Gemini quota runs out mid-demo: **nothing breaks** — every endpoint falls back to rule-based
  output automatically (verified: smoke 14/14 with quota exhausted)

## 5. Rollback / redeploy

- `autoDeploy: true` — pushing to `main` redeploys. For a demo-day freeze, flip
  `autoDeploy` → off in the render.yaml service entry, or click "Disable auto deploy" in the dashboard.
- Re-deploy cache refresh: `python scripts/refresh_cache.py` locally → commit → push (auto-deploys fresh snapshots).

## Env var quick reference

| Var | Service | Required | Notes |
|---|---|---|---|
| `OPENAQ_API_KEY` | backend | no* | fallback JSON active without it |
| `FIRMS_API_KEY` | backend | no* | you have it — live fires |
| `WAQI_TOKEN` | backend | no* | backup AQI |
| `GEMINI_API_KEY` | backend | no* | dedicated deploy key preferred |
| `GEMINI_RETRIES` | backend | no | default 5, exponential backoff |
| `BACKEND_URL` | frontend | auto | set by blueprint (`hostport`) |

\* No key → graceful fallback. That is a feature, not a bug.