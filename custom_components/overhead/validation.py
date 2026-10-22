"""Validate server settings and separate untrusted presentation options."""

import math
import re
from urllib.parse import urlsplit

DEFAULTS = {
    "name": "Overhead",
    "latitude": 0.0,
    "longitude": 0.0,
    "timezone": "UTC",
    "source": "adsb_lol",
    "receiver_url": "",
    "radius_km": "25",
    "contact": "",
    "fal_api_key": "",
    "generation_enabled": False,
    "gen_daily_usd": 1.0,
    "gen_parallel": 1,
    "logo_source": "daisycon",
    "visitor_refs": "",
    "cache_mb": 512,
}
CARD_KEYS = {
    "view",
    "period",
    "snapshot_minutes",
    "order",
    "count",
    "strip",
    "include_ground",
    "pictures",
    "paper",
    "panel",
    "labels",
    "logos",
    "colours",
    "look",
    "header",
    "footer",
    "text_size",
    "style",
    "custom_style",
    "build_medium",
    "build_period",
    "build_palette",
    "build_line",
    "build_texture",
    "build_mood",
    "build_extra",
    "model",
    "backdrop",
    "viewpoint",
    "fidelity",
    "font",
    "scale",
    "photo_fit",
    "unpainted",
    "ufo",
    "visitors",
    "title",
}


def settings_of(values):
    s = {**DEFAULTS, **values}
    for key, lo, hi in [
        ("latitude", -90, 90),
        ("longitude", -180, 180),
        ("gen_daily_usd", 0, 100),
        ("gen_parallel", 1, 3),
        ("cache_mb", 64, 4096),
    ]:
        value = float(s[key])
        if not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f"Invalid {key}")
        s[key] = int(value) if key in ("gen_parallel", "cache_mb") else value
    if s["source"] not in ("adsb_lol", "receiver"):
        raise ValueError("Invalid source")
    if str(s["radius_km"]) not in ("5", "10", "15", "25", "35", "50", "80"):
        raise ValueError("Invalid radius_km")
    s["radius_km"] = str(s["radius_km"])
    if s["source"] == "receiver":
        u = urlsplit(s["receiver_url"])
        if (
            u.scheme not in ("http", "https")
            or not u.hostname
            or u.username
            or u.password
        ):
            raise ValueError("Receiver must be an http(s) URL without credentials")
    if s["generation_enabled"] and not s["fal_api_key"]:
        raise ValueError("A fal.ai key is required to enable generation")
    from zoneinfo import ZoneInfo

    ZoneInfo(s["timezone"])
    return s


def profile_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", value):
        raise ValueError(
            "profile_id must contain 1–64 letters, numbers, underscores or hyphens"
        )
    return value


def options_of(values):
    if not isinstance(values, dict) or set(values) - CARD_KEYS:
        raise ValueError("Unknown or server-only card option")
    import json

    if len(json.dumps(values, allow_nan=False)) > 12000:
        raise ValueError("Card options too large")
    o = {
        "view": "photo",
        "pictures": "photos",
        "period": "now",
        "snapshot_minutes": 60,
        **values,
    }
    if o["view"] not in ("photo", "plate", "cluster", "scene"):
        raise ValueError("Invalid card view")
    if o["period"] not in ("now", "since"):
        raise ValueError("Invalid period")
    n = float(o["snapshot_minutes"])
    if not math.isfinite(n) or not 1 <= n <= 1440:
        raise ValueError("snapshot_minutes must be between 1 and 1440")
    o["snapshot_minutes"] = n
    if "labels" in o and (
        not isinstance(o["labels"], list)
        or any(not isinstance(v, str) for v in o["labels"])
    ):
        raise ValueError("labels must be a list of strings")
    return o
