"""Download and cache SuC Tracker Europe pricing JSON."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger(__name__)

DEFAULT_URL = "https://suc-tracker.eu/data/europe.json"


def fetch_prices(
    *,
    url: str = DEFAULT_URL,
    cache_dir: str | Path = "/cache",
    ttl_seconds: int = 43_200,
    timeout: float = 60.0,
) -> dict[str, Any]:
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    cache_file = cache_path / "europe.json"
    meta_file = cache_path / "europe.meta.json"

    if cache_file.exists() and meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            age = time.time() - float(meta.get("fetched_at", 0))
            if age < ttl_seconds:
                log.info("Using cached rates (age %.0fs)", age)
                return json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            log.warning("Cache unreadable (%s); re-fetching", exc)

    log.info("Downloading rates…")
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(
            url,
            headers={"Accept": "application/json", "User-Agent": "suc-estimator/0.1"},
        )
        resp.raise_for_status()
        data = resp.json()

    cache_file.write_text(json.dumps(data), encoding="utf-8")
    meta_file.write_text(
        json.dumps({"fetched_at": time.time(), "url": url}), encoding="utf-8"
    )
    return data
