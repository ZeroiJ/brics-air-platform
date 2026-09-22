#!/usr/bin/env python3
"""Smoke test — verify every endpoint responds with the expected shape.

Self-contained: uses FastAPI TestClient (no server needed).
Optional: --base-url https://... to test a deployed instance instead.

Usage:
    python scripts/smoke_test.py
    python scripts/smoke_test.py --base-url https://your-backend.onrender.com

Exit code 0 = all pass, 1 = failures.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx  # noqa: E402

CHECKS: list[dict] = []


def _client(base_url: str | None):
    if base_url:
        return httpx.Client(base_url=base_url, timeout=30)
    from fastapi.testclient import TestClient  # noqa: E402
    from backend.main import app  # noqa: E402

    return TestClient(app)


def add(method: str, path: str, status: int = 200, keys: list[str] | None = None) -> None:
    CHECKS.append(dict(method=method, path=path, status=status, keys=keys or []))


def run(base_url: str | None) -> int:
    add("GET", "/health", keys=["status"])
    add("GET", "/api/cities", keys=["city", "country"])
    add("GET", "/api/meta", keys=["service"])
    add("GET", "/api/status", keys=["sources", "overall", "gemini"])
    add("GET", "/api/aqi", keys=["city", "aqi", "pm25", "source"])
    add("GET", "/api/aqi?city=Delhi", keys=["city", "aqi", "pm25"])
    add("GET", "/api/aqi?city=Atlantis", status=404)
    add("GET", "/api/fires?limit=50", keys=["lat", "lng", "frp"])
    add("GET", "/api/meteo?city=Delhi", keys=["wind_direction_label", "humidity_pct"])
    add("GET", "/api/sensors?country=IN", keys=["city", "pm25", "source"])
    add("GET", "/api/analysis?city=Delhi", keys=["risk_level", "cross_border_suspected"])
    add("GET", "/api/forecast?city=Delhi", keys=["forecast_24h_aqi", "spike_warning"])
    add("GET", "/api/crossborder", keys=["source_country", "affected_city"])
    add("GET", "/api/alerts?city=Delhi", keys=["message_hindi", "message_portuguese", "message_english"])
    add("POST", "/api/analyze-photo", status=200,
        keys=["pollution_type", "severity_score", "confidence"])

    c = _client(base_url)
    failures = 0
    total = len(CHECKS)
    for i, ch in enumerate(CHECKS, 1):
        try:
            if ch["method"] == "GET":
                r = c.get(ch["path"])
            else:
                r = c.post(ch["path"], data={"city": "Delhi"},
                           files={"file": ("smog.jpg", b"\xff\xd8fake" * 200, "image/jpeg")})
            data = r.json()
            ok_status = r.status_code == ch["status"]
            ok_keys = all(k in data for k in ch["keys"])
            # nested: /api/cities returns list; check key present in first element
            if isinstance(data, list) and data and all(k in data[0] for k in ch["keys"]):
                ok_keys = True
            ok = ok_status and ok_keys
            print(f"  [{'PASS' if ok else 'FAIL'}] {i:>2}/{total} {ch['method']} {ch['path']} -> {r.status_code}")
            if not ok:
                failures += 1
        except Exception as e:  # noqa: BLE001
            print(f"  [FAIL] {i:>2}/{total} {ch['method']} {ch['path']} -> EXC {type(e).__name__}: {e}")
            failures += 1

    print(f"\n{total - failures}/{total} passed" + ("" if failures == 0 else f" — {failures} FAILED"))
    return 1 if failures else 0


if __name__ == "__main__":
    base = None
    if "--base-url" in sys.argv:
        base = sys.argv[sys.argv.index("--base-url") + 1]
        base = base.rstrip("/")
    sys.exit(run(base))