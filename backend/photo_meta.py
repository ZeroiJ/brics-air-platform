"""EXIF GPS extraction from citizen-uploaded photos.

Why this exists
---------------
The PS asks us to combine citizen-sourced data. Rather than making a citizen
type an address or click a map, we read the GPS coordinates the phone already
embeds in the photo (EXIF tag 0x8825). One upload -> location, for free.

Design rule: this module NEVER raises. It sits in the photo-upload request path,
and a malformed or EXIF-less image must degrade to "no location" rather than
break the upload or 500 the endpoint.

What is NOT stored
------------------
Per the team's decision we do not persist image bytes — only the Gemini verdict,
the coordinates, and a SHA-256 for duplicate detection. `image_bytes` records the
size so a reviewer can see how much evidence the pipeline chose not to keep.
"""
from __future__ import annotations

import io
from typing import Optional

# EXIF GPS IFD pointer, per the Exif 2.3 spec.
_GPS_IFD = 0x8825


def _dms_to_decimal(dms, ref: str) -> Optional[float]:
    """Convert EXIF (degrees, minutes, seconds) to signed decimal degrees."""
    try:
        d, m, s = (float(v) for v in dms)
    except (TypeError, ValueError):
        return None
    if d < 0 or m < 0 or s < 0:  # malformed
        return None
    decimal = d + m / 60.0 + s / 3600.0
    if str(ref).upper() in ("S", "W"):
        decimal = -decimal
    return round(decimal, 6)


def extract_gps(data: bytes) -> tuple[Optional[float], Optional[float], str]:
    """Return ``(lat, lng, source)`` from raw image bytes.

    ``source`` is one of:
      - ``"exif_gps"`` — real coordinates from the photo
      - ``"none"``     — no usable GPS in the file (PC shots, stripped EXIF, PNG)

    Always returns a 3-tuple. Never raises.
    """
    if not data:
        return None, None, "none"
    try:
        from PIL import Image, ExifTags  # noqa: PLC0415 - optional at import time

        img = Image.open(io.BytesIO(data))
        exif = img.getexif()
        if not exif or _GPS_IFD not in exif:
            return None, None, "none"
        gps = exif.get_ifd(_GPS_IFD)
        if not gps:
            return None, None, "none"
        named = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps.items()}
        lat = _dms_to_decimal(named.get("GPSLatitude"), named.get("GPSLatitudeRef", "N"))
        lng = _dms_to_decimal(named.get("GPSLongitude"), named.get("GPSLongitudeRef", "E"))
        if lat is None or lng is None:
            return None, None, "none"
        # Reject null island and out-of-range values — those are the classic
        # "EXIF present but zeroed" signature, and a real report at 0,0 would
        # silently route to the wrong authority.
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            return None, None, "none"
        if abs(lat) < 1e-6 and abs(lng) < 1e-6:
            return None, None, "none"
        return lat, lng, "exif_gps"
    except Exception:  # noqa: BLE001 - corrupt file, unsupported format, missing PIL
        return None, None, "none"
