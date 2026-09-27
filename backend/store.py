"""Citizen report storage — Neon Postgres, with a local-file fallback.

Why Postgres and not the existing SQLite layer
----------------------------------------------
Render's free tier has an ephemeral filesystem: the container's disk is wiped on
every deploy and every restart, so `backend/database.py` (SQLite) cannot hold
citizen evidence. Neon is a hosted Postgres that survives deploys, and its free
tier is more than enough when we store no image bytes (see `photo_meta`).

Reliability rule
----------------
**This module never raises.** It sits in the photo-upload request path. If
`DATABASE_URL` is missing, Neon is unreachable, or the write fails, the report
still gets recorded to a local JSON file and the caller is told which backend
accepted it. A citizen's report is never silently dropped because a database
had a bad minute — and a failed write must never fail the upload itself.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.gemini.alerts import AUTHORITIES

LOCAL_PATH = Path(__file__).parent / "cache" / "citizen_reports.json"

# Neon's free tier scales to zero after a few idle minutes; the first query
# wakes it. A short timeout keeps a cold-start from stalling the upload.
_CONNECT_TIMEOUT = 10

_COLUMNS = (
    "report_id", "submitted_at", "city", "country", "lat", "lng",
    "location_source", "citizen_description", "pollution_type",
    "estimated_aqi_category", "visibility_km", "severity_score", "likely_source",
    "recommendation", "confidence", "verdict_engine", "image_bytes", "image_sha256",
    "routed_authority", "urgency", "delivery_status", "dispatched_at",
)

# Severity bands -> urgency. Deliberately conservative: a citizen upload is
# unverified eyewitness evidence, so it routes as `advisory` unless the vision
# model is confident, and never as `watch` if the report is severe.
def _urgency_for(severity: Optional[int], confidence: Optional[float]) -> str:
    if severity is None:
        return "watch"
    if severity >= 8 and (confidence or 0) >= 0.6:
        return "immediate"
    if severity >= 5:
        return "advisory"
    return "watch"


def _dsn() -> str:
    return (os.getenv("DATABASE_URL") or "").strip()


def backend_available() -> bool:
    return bool(_dsn())


def _connect():
    import psycopg  # noqa: PLC0415 - imported lazily so a missing driver can't break import

    return psycopg.connect(_dsn(), connect_timeout=_CONNECT_TIMEOUT)


# --- Neon Postgres -----------------------------------------------------------
def _save_postgres(rec: dict[str, Any]) -> Optional[str]:
    """Write to Neon. Returns None on success, or an error string on failure."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            placeholders = ", ".join(["%s"] * len(_COLUMNS))
            cols = ", ".join(_COLUMNS)
            cur.execute(
                f"INSERT INTO citizen_reports ({cols}) VALUES ({placeholders}) "
                f"ON CONFLICT (report_id) DO NOTHING",
                [rec.get(c) for c in _COLUMNS],
            )
        return None
    except Exception as exc:  # noqa: BLE001
        return f"{exc.__class__.__name__}: {exc}"[:200]


def _read_postgres(limit: int, city: Optional[str]) -> Optional[list[dict[str, Any]]]:
    try:
        with _connect() as conn, conn.cursor() as cur:
            if city:
                cur.execute(
                    "SELECT * FROM citizen_reports WHERE city = %s "
                    "ORDER BY submitted_at DESC LIMIT %s", (city, limit))
            else:
                cur.execute(
                    "SELECT * FROM citizen_reports ORDER BY submitted_at DESC LIMIT %s",
                    (limit,))
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return None


# --- Local JSON fallback -----------------------------------------------------
def _load_local() -> list[dict[str, Any]]:
    try:
        if LOCAL_PATH.exists():
            data = json.loads(LOCAL_PATH.read_text())
            if isinstance(data, list):
                return data
    except Exception:  # noqa: BLE001
        pass
    return []


def _save_local(rec: dict[str, Any]) -> None:
    rows = _load_local()
    rows.insert(0, rec)
    LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_PATH.write_text(json.dumps(rows[:500], indent=2, default=str))


# --- Public API --------------------------------------------------------------
def save_report(
    *,
    city: str,
    verdict: Any,
    description: str = "",
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    location_source: str = "none",
    image_bytes: int = 0,
    image_sha256: str = "",
    verdict_engine: str = "rule_fallback",
    country: str = "",
) -> dict[str, Any]:
    """Record one citizen report. Never raises.

    Returns ``{"ok", "store", "report_id", "routed_authority", "urgency",
    "delivery_status", "error"?}``.
    """
    sev = getattr(verdict, "severity_score", None)
    conf = getattr(verdict, "confidence", None)
    authority = AUTHORITIES.get(city, "Local Environment Authority")
    rec: dict[str, Any] = {
        "report_id": uuid.uuid4().hex[:16],
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "country": country,
        "lat": lat,
        "lng": lng,
        "location_source": location_source,
        "citizen_description": (description or "").strip()[:2000] or None,
        "pollution_type": getattr(verdict, "pollution_type", None),
        "estimated_aqi_category": getattr(verdict, "estimated_aqi_category", None),
        "visibility_km": getattr(verdict, "visibility_km", None),
        "severity_score": sev,
        "likely_source": getattr(verdict, "likely_source", None),
        "recommendation": getattr(verdict, "recommendation", None),
        "confidence": conf,
        "verdict_engine": verdict_engine,
        "image_bytes": image_bytes,
        "image_sha256": image_sha256,
        "routed_authority": authority,
        "urgency": _urgency_for(sev, conf),
        # Honest by construction: we record the routing decision, we do not
        # claim a message was sent to anyone. See docs/PS_COVERAGE.md.
        "delivery_status": "recorded",
        "dispatched_at": None,
    }

    store = "local"
    error = None
    if _dsn():
        error = _save_postgres(rec)
        if error is None:
            store = "neon"
    if store != "neon":
        try:
            _save_local(rec)
        except Exception as exc:  # noqa: BLE001
            error = error or f"local write failed: {exc.__class__.__name__}"

    out = {k: rec[k] for k in
           ("report_id", "routed_authority", "urgency", "delivery_status")}
    out.update(ok=True, store=store, location_source=rec["location_source"])
    if error:
        out["error"] = error
    return out


def recent_reports(limit: int = 20, city: Optional[str] = None) -> dict[str, Any]:
    """Return ``{"reports", "store", "total"}``. Degrades to local, never raises."""
    limit = max(1, min(int(limit), 100))
    if _dsn():
        rows = _read_postgres(limit, city)
        if rows is not None:
            return {"reports": rows, "store": "neon", "total": len(rows)}
    rows = _load_local()[:limit]
    if city:
        rows = [r for r in rows if str(r.get("city", "")).lower() == city.lower()]
    return {"reports": rows, "store": "local", "total": len(rows)}
