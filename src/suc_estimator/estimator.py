"""Match sessions to stations and estimate costs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from suc_estimator.db import ChargingSession
from suc_estimator.geo import nearest
from suc_estimator.pricing import Station, micro_to_currency, rate_at

SUC_NAME_RE = re.compile(r"supercharger|\bsuc\b|tesla\s*sc", re.I)


@dataclass(frozen=True)
class EstimateResult:
    session_id: int
    station_id: str | None
    station_name: str | None
    distance_m: float | None
    energy_kwh: float | None
    rate_per_kwh: float | None
    currency: str | None
    cost: float | None
    status: str
    detail: str = ""


def session_energy_kwh(session: ChargingSession) -> float | None:
    candidates = [v for v in (session.charge_energy_used, session.charge_energy_added) if v is not None]
    if not candidates:
        return None
    return max(float(c) for c in candidates)


def looks_like_supercharger(session: ChargingSession) -> bool:
    return bool(session.geofence_name and SUC_NAME_RE.search(session.geofence_name))


def crosses_tou_window(station: Station, session: ChargingSession) -> bool:
    """True if start and end fall in different tariff windows (or end has no window)."""
    if session.end_date is None:
        return False
    start_window = rate_at(station, session.start_date)
    end_window = rate_at(station, session.end_date)
    if start_window is None or end_window is None:
        return start_window is not end_window
    return (
        start_window.price_micro != end_window.price_micro
        or start_window.start_minute != end_window.start_minute
        or start_window.end_minute != end_window.end_minute
        or start_window.days != end_window.days
    )


def estimate_session(
    session: ChargingSession,
    stations: list[Station],
    *,
    match_radius_m: float = 400.0,
    allow_cross_tou: bool = False,
) -> EstimateResult:
    energy = session_energy_kwh(session)
    if energy is None or energy <= 0:
        return EstimateResult(
            session.id, None, None, None, energy, None, None, None, "skip", "no energy"
        )

    if session.lat is None or session.lon is None:
        return EstimateResult(
            session.id, None, None, None, energy, None, None, None, "skip", "no coordinates"
        )

    match = nearest(
        session.lat,
        session.lon,
        stations,
        lambda s: (s.lat, s.lon),
        match_radius_m,
    )
    if match is None:
        return EstimateResult(
            session.id,
            None,
            None,
            None,
            energy,
            None,
            None,
            None,
            "unmatched",
            f"no station within {match_radius_m:.0f} m",
        )

    station, distance = match
    window = rate_at(station, session.start_date)
    if window is None:
        return EstimateResult(
            session.id,
            station.id,
            station.name,
            distance,
            energy,
            None,
            station.currency,
            None,
            "skip",
            "no tariff window for start time",
        )

    if not allow_cross_tou and crosses_tou_window(station, session):
        return EstimateResult(
            session.id,
            station.id,
            station.name,
            distance,
            energy,
            None,
            station.currency,
            None,
            "skip",
            "crosses time-of-use rate change (opt in with --allow-cross-tou)",
        )

    rate = micro_to_currency(window.price_micro)
    cost = round(energy * rate, 2)
    return EstimateResult(
        session_id=session.id,
        station_id=station.id,
        station_name=station.name,
        distance_m=distance,
        energy_kwh=energy,
        rate_per_kwh=rate,
        currency=station.currency,
        cost=cost,
        status="ok",
        detail=f"{energy:.3f} kWh × {rate:.4f} {station.currency}/kWh @ {distance:.0f} m",
    )
