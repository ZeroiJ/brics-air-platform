"""Shared wiring for Sarthak's Gemini modules.

One place for: lazy client singleton, tenacity retry policy, and robust
structured-JSON extraction. Public modules (aqi_analysis, forecast,
crossborder, alerts, photo_analysis) import from here so the Gemini
integration stays consistent.

Design notes
------------
- Importing this module never calls the API and never requires a key:
  the client is created lazily on first use. This keeps `backend.main`
  importable in CI / frontend environments without GEMINI_API_KEY.
- Modules raise on failure (no key, API error, schema mismatch) and let
  `backend.main` fall back to Sujal's rule-based stand-ins — never crash.
- Tenacity: 3 attempts, exponential backoff, only retried on API errors
  (transient 429/5xx), not on our own programming mistakes.
"""
from __future__ import annotations

import json
import os
from typing import TypeVar

from dotenv import load_dotenv
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Load .env so GEMINI_API_KEY is available without extra setup steps.
load_dotenv()

from google import genai  # noqa: E402
from google.genai import errors, types  # noqa: E402

# ---------------------------------------------------------------------------
# Geo helpers (shared by forecast + crossborder)
# ---------------------------------------------------------------------------
def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km between two lat/lng points."""
    import math

    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))

# ---------------------------------------------------------------------------
# Client singleton
# ---------------------------------------------------------------------------
_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Return a lazily-created Gemini client, or raise if no API key set.

    Explicit HTTP timeout: the public API can be slow under load (observed
    10-15s for a trivial call) — the SDK default was timing out and spinning
    into internal retries that looked like hangs.
    """
    global _client
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set — copy .env.example to .env and add your key")
    if _client is None:
        _client = genai.Client(
            api_key=key,
            http_options=types.HttpOptions(timeout=180_000),  # ms; generous
        )
    return _client


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------
def gemini_retry(func):
    """Retry transient API failures with exponential backoff.

    Default: 5 attempts (2s/4s/8s/16s waits). The API returns 503-high-demand
    in waves; override attempts with GEMINI_RETRIES if needed.
    """
    import os as _os

    attempts = int(_os.getenv("GEMINI_RETRIES", "5"))
    return retry(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=1, min=2, max=16),
        retry=retry_if_exception_type((errors.APIError, errors.ClientError)),
        reraise=True,
    )(func)


# ---------------------------------------------------------------------------
# Structured output extraction
# ---------------------------------------------------------------------------
T = TypeVar("T")


def _as_dict(obj) -> dict:
    """Normalize a parsed SDK object into a plain dict."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return obj


def _extract_raw(response) -> dict | list:
    """Return the JSON dict/list from a Gemini response (parsed or text)."""
    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        if isinstance(parsed, list):
            return [_as_dict(p) for p in parsed]
        return _as_dict(parsed)

    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned empty content")
    # Strip markdown fences if the model wrapped JSON in ```json ... ```
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def to_model(response, schema_cls: type[T] | list[type]) -> T | list[T]:
    """Turn a Gemini structured-JSON response into validated Pydantic object(s).

    Accepts a Pydantic model class OR `list[SomeModel]` (which returns a list,
    validated element-by-element). Uses `response.parsed` when the SDK already
    decoded it, else parses `response.text` as JSON.
    """
    from typing import get_args, get_origin

    if response is None:
        raise RuntimeError("Gemini returned no response object")

    raw = _extract_raw(response)

    if get_origin(schema_cls) is list:
        item_cls = get_args(schema_cls)[0]
        if not isinstance(raw, list):
            raise RuntimeError(
                f"Expected a JSON list for {schema_cls}, got {type(raw).__name__}"
            )
        return [item_cls.model_validate(x) for x in raw]
    return schema_cls.model_validate(raw)