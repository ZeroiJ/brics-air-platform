"""Final integration check (24 Sep): all four data sources + Gemini live.

Expects, after OPENAQ/FIRMS/WAQI/GEMINI keys in .env + radius fix:
  [1] /api/status -> openaq=live, firms=live (meteo/sensors live, waqi backup)
  [2] /api/aqi    -> readings sourced from OpenAQ (live per-city values)
  [3] /api/fires  -> live FIRMS rows (fallback is only 12 hotspots)
  [4] /api/meta   -> gemini_live True

Exit 0 = all checks passed.
"""
from __future__ import annotations

import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
FALLBACK_FIRE_COUNT = 12
FALLBACK_AQI = {"Delhi": 287, "Mumbai": 132}  # exact mock fingerprints


def wait_health(timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"{BASE}/health", timeout=2).status_code == 200:
                return True
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    return False


def main() -> None:
    if not wait_health():
        print("[FATAL] backend did not come up")
        sys.exit(2)

    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        results.append((name, ok, detail))

    # --- 1) /api/status ------------------------------------------------------
    st = httpx.get(f"{BASE}/api/status", timeout=30).json()
    srcs = st.get("sources", st if isinstance(st, list) else [])
    by_name = {s.get("source"): s for s in srcs if isinstance(s, dict)}
    for name in ("openaq", "waqi", "firms", "meteo", "sensors"):
        s = by_name.get(name)
        if s:
            print(f"   {name:<9} -> {s.get('status')}: {str(s.get('detail'))[:90]}")
    check("openaq marked live", str(by_name.get("openaq", {}).get("status", "")).lower() == "live",
          f"status={by_name.get('openaq', {}).get('status')!r}")
    check("firms marked live", str(by_name.get("firms", {}).get("status", "")).lower() == "live",
          f"status={by_name.get('firms', {}).get('status')!r}")

    # --- 2) /api/aqi (live OpenAQ path) --------------------------------------
    readings = httpx.get(f"{BASE}/api/aqi", timeout=120).json()
    rows = [r for r in readings if isinstance(r, dict)]
    print(f"[aqi] {len(rows)} rows; sources={sorted({r.get('source') for r in rows})}")
    for r in rows:
        live_hint = "LIVE" if str(r.get("timestamp"))[:10] == time.strftime("%Y-%m-%d") else "stale"
        print(f"   {r.get('city'):<14} aqi={r.get('aqi')} pm25={r.get('pm25')} src={r.get('source')} [{live_hint}] {str(r.get('timestamp'))[:19]}")
    n_openaq = sum(1 for r in rows if r.get("source") == "openaq")
    check("aqi rows are live OpenAQ", n_openaq >= 3, f"{n_openaq}/{len(rows)} rows source=openaq")

    # --- 3) /api/fires -------------------------------------------------------
    fires = httpx.get(f"{BASE}/api/fires", timeout=120).json()
    nfires = len(fires)
    print(f"[fires] {nfires} hotspots")
    check("fires live (not 12-row fallback)", nfires > FALLBACK_FIRE_COUNT, f"{nfires} rows")

    # --- 4) /api/meta --------------------------------------------------------
    meta = httpx.get(f"{BASE}/api/meta", timeout=30).json()
    check("gemini still live", bool(meta.get("gemini_live")), f"gemini_live={meta.get('gemini_live')}")

    npass = sum(1 for _, ok, _ in results if ok)
    print(f"[done] {npass}/{len(results)} checks passed")
    sys.exit(0 if npass == len(results) else 1)


if __name__ == "__main__":
    main()