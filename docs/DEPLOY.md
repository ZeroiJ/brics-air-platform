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

## 1. Blueprint deploy (10 min)

1. Render dashboard → **New → Blueprint**
2. Select `ZeroiJ/brics-air-platform` → Render auto-reads `render.yaml`
3. It will ask you to fill the 4 secret env vars (`sync: false` = secure, prompted):
   - Backend: `OPENAQ_API_KEY`, `FIRMS_API_KEY`, `WAQI_TOKEN`, `GEMINI_API_KEY`
   - Frontend: nothing — `BACKEND_URL` resolves automatically to the internal URL
4. **Apply** → two services build in parallel

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