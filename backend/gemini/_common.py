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
# Client singleton
# ---------------------------------------------------------------------------
_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Return a lazily-created Gemini client, or raise if no API key set."""
    global _client
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set — copy .env.example to .env and add your key")
    if _client is None:
        _client = genai.Client(api_key=key)
    return _client


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------
def gemini_retry(func):
    """Retry transient API failures 3x with exponential backoff (2s/4s/8s)."""
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type((errors.APIError, errors.ClientError)),
        reraise=True,
    )(func)


# ---------------------------------------------------------------------------
# Structured output extraction
# ---------------------------------------------------------------------------
T = TypeVar("T")


def to_model(response: types.GenerateContentResponse, schema_cls: type[T]) -> T:
    """Turn a Gemini structured-JSON response into a validated Pydantic model.

    Two extraction paths, newest SDK first:
      1. `response.parsed` — populated automatically when response_schema is
         given (google-genai 1.x+).
      2. Parse `response.text` as JSON and validate through Pydantic.
    Falls back to the exact error being re-raised so callers know why.
    """
    if response is None:
        raise RuntimeError("Gemini returned no response object")

    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        try:
            return schema_cls.model_validate(
                parsed.model_dump() if hasattr(parsed, "model_dump") else parsed
            )
        except Exception:
            # parsed exists but doesn't conform — fall through to JSON path
            pass

    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned empty content")

    # Strip markdown fences if the model wrapped JSON in ```json ... ```
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    data = json.loads(text)
    return schema_cls.model_validate(data)