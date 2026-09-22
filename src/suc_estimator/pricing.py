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
class MinuteTier:
    """Per-minute price for one charging-power bracket (e.g. 0–60 kW)."""

    min_power_kw: float
    max_power_kw: float | None  # None = no upper bound
    price_micro: int


@dataclass(frozen=True)
class MinuteWindow:
    """Time-of-day window with tiered per-minute prices."""

    days: int
    start_minute: int
    end_minute: int
    tiers: tuple[MinuteTier, ...]


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
    minute_windows: tuple[MinuteWindow, ...] = ()


def micro_to_currency(value: int | float) -> float:
    return float(value) / MICRO


def weekday_bit(dt: datetime) -> int:
    """SuC Tracker day bit for a timezone-aware datetime (Mon=1 … Sun=64)."""
    return 1 << dt.weekday()


def select_window(
    windows: Sequence[PriceWindow | MinuteWindow], when: datetime
) -> PriceWindow | MinuteWindow | None:
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
    minute_prices = block.get("minutePrices") or []
    if status and status not in {"available", "ok"} and not prices and not minute_prices:
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
    minute_windows: list[MinuteWindow] = []
    for p in minute_prices:
        tiers: list[MinuteTier] = []
        for t in p.get("tiers") or []:
            try:
                tiers.append(
                    MinuteTier(
                        min_power_kw=float(t["minPowerKw"]),
                        max_power_kw=(
                            float(t["maxPowerKw"]) if t.get("maxPowerKw") is not None else None
                        ),
                        price_micro=int(t["price"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        if not tiers:
            continue
        try:
            minute_windows.append(
                MinuteWindow(
                    days=int(p["days"]),
                    start_minute=int(p["start"]),
                    end_minute=int(p["end"]),
                    tiers=tuple(tiers),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    if not windows and not minute_windows:
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
            minute_windows=tuple(minute_windows),
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


def rate_at(
    station: Station, when_utc: datetime
) -> PriceWindow | MinuteWindow | None:
    when_local = localize(when_utc, station.timezone)
    if station.pricing_unit == "minute" and station.minute_windows:
        return select_window(station.minute_windows, when_local)
    return select_window(station.windows, when_local)


def tier_for_power(tiers: Sequence[MinuteTier], avg_power_kw: float) -> MinuteTier | None:
    """Per-minute tier whose power bracket contains the given average power.

    Brackets are half-open [min, max): an average power exactly at a tier's
    max falls into the next (higher) tier, matching how the published tiers
    read (``0-60``, ``60-100``, ...).
    """
    for t in tiers:
        if avg_power_kw < t.min_power_kw:
            continue
        if t.max_power_kw is None or avg_power_kw < t.max_power_kw:
            return t
    return None
