"""Public Supercharger tariff helpers (SuC Tracker schema)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

MICRO = 1_000_000


@dataclass(frozen=True)
class PriceWindow:
    days: int  # bitmask: Mon=1, Tue=2, ..., Sun=64
    start_minute: int
    end_minute: int
    price_micro: int


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    country: str
    lat: float
    lon: float
    timezone: str
    currency: str
    windows: tuple[PriceWindow, ...]
    pricing_unit: str


def micro_to_currency(value: int | float) -> float:
    return float(value) / MICRO


def weekday_bit(dt: datetime) -> int:
    """SuC Tracker day bit for a timezone-aware datetime (Mon=1 … Sun=64)."""
    return 1 << dt.weekday()


def select_window(windows: Sequence[PriceWindow], when: datetime) -> PriceWindow | None:
    if when.tzinfo is None:
        raise ValueError("when must be timezone-aware")
    bit = weekday_bit(when)
    minute = when.hour * 60 + when.minute
    for w in windows:
        if (w.days & bit) == 0:
            continue
        if w.start_minute <= minute < w.end_minute:
            return w
    return None


def parse_station(raw: Mapping[str, Any], family: str = "tesla") -> Station | None:
    pricing_root = raw.get("pricing") or {}
    key = "tesla" if family.lower() in {"tesla", "owner"} else "nonTesla"
    block = pricing_root.get(key)
    if not block:
        return None
    status = str(block.get("pricingStatus") or block.get("pricing_status") or "").lower()
    prices = block.get("prices") or []
    if status and status not in {"available", "ok"} and not prices:
        return None
    unit = str(block.get("pricingUnit") or block.get("pricing_unit") or "kwh").lower()
    windows: list[PriceWindow] = []
    for p in prices:
        try:
            windows.append(
                PriceWindow(
                    days=int(p["days"]),
                    start_minute=int(p["start"]),
                    end_minute=int(p["end"]),
                    price_micro=int(p["price"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    if unit != "kwh" or not windows:
        return None
    try:
        return Station(
            id=str(raw["id"]),
            name=str(raw.get("name") or raw["id"]),
            country=str(raw.get("country") or ""),
            lat=float(raw["lat"]),
            lon=float(raw["lon"]),
            timezone=str(raw.get("timezone") or "Europe/Berlin"),
            currency=str(block.get("currency") or "EUR"),
            windows=tuple(windows),
            pricing_unit=unit,
        )
    except (KeyError, TypeError, ValueError):
        return None


def load_stations(payload: Mapping[str, Any], family: str = "tesla") -> list[Station]:
    return [
        st
        for raw in (payload.get("stations") or [])
        if (st := parse_station(raw, family=family)) is not None
    ]


def localize(when: datetime, tz_name: str) -> datetime:
    if when.tzinfo is None:
        when = when.replace(tzinfo=ZoneInfo("UTC"))
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Europe/Berlin")
    return when.astimezone(tz)


def rate_at(station: Station, when_utc: datetime) -> PriceWindow | None:
    return select_window(station.windows, localize(when_utc, station.timezone))
