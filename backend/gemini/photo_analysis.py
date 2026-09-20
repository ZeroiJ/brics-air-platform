"""Sarthak — Module 5: Citizen photo vision analysis (Gemini Vision).

Input:  CitizenPhoto (base64-encoded image + city)
Output: GeminiPhotoResult

Contract with Sujal's backend (backend/main.py):
    result = gem_photo.analyze_photo(photo)
Raises on failure -> main.py serves its honest low-confidence placeholder.

Note: `CitizenPhoto` carries no MIME type, so we sniff magic bytes to send
the image in its true format.
"""
from __future__ import annotations

import base64
import os

from google.genai import types

from backend.gemini._common import gemini_retry, get_client, to_model
from backend.models import CitizenPhoto, GeminiPhotoResult

MODEL = os.getenv("GEMINI_PHOTO_MODEL", "gemini-3.6-flash")


def sniff_mime(data: bytes) -> str:
    """Detect image format from magic bytes (JPEG/PNG/WebP/GIF, default JPEG)."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/jpeg"


SYSTEM_PROMPT = (
    "You are a trained environmental analyst assessing citizen photo evidence "
    "of air pollution for the BRICS Climate Intelligence Platform. Judge the "
    "photo itself: what type of pollution is visible (haze, smog, smoke, dust, "
    "clear sky), estimate visibility distance, rate severity 1-10 "
    "(10 = worst), infer the likely source, and give one practical health "
    "recommendation. If the photo shows no clear pollution, set "
    "pollution_visible=false and explain. Return structured JSON."
)


@gemini_retry
def _call_gemini(photo: CitizenPhoto) -> GeminiPhotoResult:
    client = get_client()
    try:
        payload = base64.b64decode(photo.image_base64)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"image_base64 is not valid base64: {exc}") from exc
    if not payload:
        raise ValueError("image_base64 decodes to empty bytes")

    image_part = types.Part.from_bytes(data=payload, mime_type=sniff_mime(payload))
    prompt = (
        f"Analyze this citizen-submitted photo from {photo.city}. "
        "Describe what pollution is visible, estimate visibility in km, "
        "rate severity from 1 (clean) to 10 (extreme), identify the likely "
        "source, and give a health recommendation. Return structured JSON only."
    )
    response = client.models.generate_content(
        model=MODEL,
        contents=[prompt, image_part],
        config={
            "system_instruction": SYSTEM_PROMPT,
            "response_mime_type": "application/json",
            "response_schema": GeminiPhotoResult.model_json_schema(),
            "temperature": 0.2,
        },
    )
    return to_model(response, GeminiPhotoResult)


def analyze_photo(photo: CitizenPhoto) -> GeminiPhotoResult:
    """Gemini Vision analysis of a citizen photo (Sujal's contract)."""
    result = _call_gemini(photo)
    # Ground-truth constraints from the contract.
    result.severity_score = min(max(result.severity_score, 1), 10)
    result.confidence = round(min(max(result.confidence, 0.0), 1.0), 2)
    return result