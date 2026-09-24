"""Live verification of Gemini Modules 3-5 (crossborder, alerts, photo_analysis).

Runs against the LOCAL backend (assumes uvicorn on 127.0.0.1:8000 with
GEMINI_API_KEY set so the routes take the live Gemini path, not rules).

Checks (combined 23-24 Sep milestone):
  [M3] /api/crossborder        -> structured list of GeminiCrossBorderEvent
  [M4] /api/alerts?city=Delhi  -> AlertMessage in Hindi/Portuguese/English
  [M5] POST /api/analyze-photo -> GeminiPhotoResult from a synthetic hazy JPEG

Exit 0 = all checks passed.
"""
from __future__ import annotations

import io
import sys
import time

import requests

BASE = "http://127.0.0.1:8000"


def check(name: str, ok: bool, detail: str) -> tuple[str, bool, str]:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return (name, ok, detail)


def main() -> None:
    results: list[tuple[str, bool, str]] = []

    # --- 0) confirm Gemini is live (not rule fallback) -----------------------
    try:
        meta = requests.get(f"{BASE}/api/meta", timeout=30).json()
    except Exception as exc:  # noqa: BLE001
        print(f"[FATAL] backend unreachable: {exc}")
        sys.exit(2)
    print(f"[meta] {meta}")
    results.append(check(
        "gemini live",
        bool(meta.get("gemini_live")),
        f"status={meta.get('gemini_status')!r} wired={meta.get('gemini_modules_wired')!r}",
    ))

    # --- 1) Module 3 — cross-border events ----------------------------------
    t0 = time.time()
    r = requests.get(f"{BASE}/api/crossborder", timeout=180)
    dt = time.time() - t0
    events = r.json()
    ok = r.status_code == 200 and isinstance(events, list)
    print(f"[crossborder] {len(events)} events in {dt:.1f}s (HTTP {r.status_code})")
    for e in (events or [])[:4]:
        if not isinstance(e, dict):
            continue
        print(f"   {e.get('source_city')} ({e.get('source_country')}) -> "
              f"{e.get('affected_city')} ({e.get('affected_country')}) | "
              f"{e.get('transport_direction')} {e.get('distance_km')} km | "
              f"{e.get('severity')} | {e.get('source_cause')}")
        ev = str(e.get("evidence_summary", ""))[:150]
        print(f"     evidence: {ev}")
    results.append(check("crossborder 200 + list", ok, f"{r.status_code}"))

    # --- 2) Module 4 — trilingual authority alert ----------------------------
    t0 = time.time()
    r = requests.get(f"{BASE}/api/alerts", params={"city": "Delhi"}, timeout=180)
    dt = time.time() - t0
    a = r.json()
    ok = (
        r.status_code == 200
        and isinstance(a, dict)
        and all(a.get(k) for k in ("message_hindi", "message_portuguese", "message_english", "target_authority", "urgency"))
    )
    print(f"[alerts] Delhi in {dt:.1f}s (HTTP {r.status_code})")
    for k in ("city", "risk_level", "target_authority", "urgency"):
        print(f"   {k}: {a.get(k)!r}")
    print(f"   HI: {str(a.get('message_hindi', ''))[:130]}")
    print(f"   PT: {str(a.get('message_portuguese', ''))[:130]}")
    print(f"   EN: {str(a.get('message_english', ''))[:130]}")
    results.append(check("alerts trilingual complete", ok, f"{r.status_code}"))

    # --- 3) Module 5 — photo analysis (synthetic hazy JPEG) ------------------
    try:
        from PIL import Image, ImageDraw  # streamlit bundles pillow

        img = Image.new("RGB", (640, 480), (150, 150, 150))
        d = ImageDraw.Draw(img)
        for y in range(480):  # hazy horizon gradient
            shade = 120 + int(52 * (y / 480))
            d.line([(0, y), (640, y)], fill=(shade, shade, max(0, shade - 6)))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        jpeg_bytes = buf.getvalue()
        print(f"[photo] synthetic hazy JPEG built: {len(jpeg_bytes)} bytes")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] photo: cannot build image (pillow unavailable: {exc})")
        results.append(check("photo 200 + result", False, "pillow unavailable"))
    else:
        t0 = time.time()
        with open("_tmp_hazy.jpg", "wb") as f:  # keep for the record
            f.write(jpeg_bytes)
        r = requests.post(
            f"{BASE}/api/analyze-photo",
            files={"file": ("hazy.jpg", jpeg_bytes, "image/jpeg")},
            data={"city": "Delhi"},
            timeout=180,
        )
        dt = time.time() - t0
        p = r.json()
        ok = r.status_code == 200 and isinstance(p, dict) and "severity_score" in p
        print(f"[photo] Delhi in {dt:.1f}s (HTTP {r.status_code})")
        for k in ("pollution_visible", "pollution_type", "estimated_aqi_category",
                  "visibility_km", "severity_score", "likely_source",
                  "recommendation", "confidence"):
            print(f"   {k}: {p.get(k)!r}")
        results.append(check("photo 200 + result", ok, f"{r.status_code}"))

    print("---")
    npass = sum(1 for _, ok, _ in results if ok)
    print(f"[done] {npass}/{len(results)} checks passed")
    sys.exit(0 if npass == len(results) else 1)


if __name__ == "__main__":
    main()