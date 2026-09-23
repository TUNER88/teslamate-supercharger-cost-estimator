"""TeslaMate Postgres access."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row


@dataclass(frozen=True)
class ChargingSession:
    id: int
    start_date: datetime
    end_date: datetime | None
    charge_energy_added: float | None
    charge_energy_used: float | None
    cost: float | None
    geofence_id: int | None
    geofence_name: str | None
    lat: float | None
    lon: float | None
    car_id: int | None = None
    # "AC" or "DC" — TeslaMate Grafana rule on mode(charges.charger_phases).
    # Default DC so unit tests without an explicit type still geo-match.
    charge_type: str = "DC"


def connect(*, host: str, port: int, dbname: str, user: str, password: str) -> psycopg.Connection:
    return psycopg.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        row_factory=dict_row,
    )


def fetch_sessions(
    conn: psycopg.Connection,
    *,
    lookback_days: int = 90,
    overwrite: bool = False,
) -> list[ChargingSession]:
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    cost_clause = "" if overwrite else "AND cp.cost IS NULL"
    # AC/DC classification matches official TeslaMate Grafana:
    #   NULLIF(mode(charger_phases), 0) IS NULL → DC, else AC.
    # No charge samples → mode() is NULL → DC. Prefer attempting a SuC match
    # for sparse data rather than dropping possible Supercharger sessions.
    sql = f"""
        SELECT
            cp.id,
            cp.start_date,
            cp.end_date,
            cp.charge_energy_added,
            cp.charge_energy_used,
            cp.cost,
            cp.geofence_id,
            cp.car_id,
            g.name AS geofence_name,
            COALESCE(g.latitude, p.latitude) AS lat,
            COALESCE(g.longitude, p.longitude) AS lon,
            CASE
              WHEN NULLIF(
                (SELECT mode() WITHIN GROUP (ORDER BY c.charger_phases)
                 FROM charges c
                 WHERE c.charging_process_id = cp.id),
                0
              ) IS NULL
              THEN 'DC'
              ELSE 'AC'
            END AS charge_type
        FROM charging_processes cp
        LEFT JOIN geofences g ON g.id = cp.geofence_id
        LEFT JOIN positions p ON p.id = cp.position_id
        WHERE cp.end_date IS NOT NULL
          AND cp.start_date >= %s
          {cost_clause}
        ORDER BY cp.start_date DESC
    """
    with conn.cursor() as cur:
        cur.execute(sql, (since,))
        rows = cur.fetchall()

    out: list[ChargingSession] = []
    for r in rows:
        out.append(
            ChargingSession(
                id=int(r["id"]),
                start_date=_as_dt(r["start_date"]),
                end_date=_as_dt(r["end_date"]) if r["end_date"] else None,
                charge_energy_added=_as_float(r["charge_energy_added"]),
                charge_energy_used=_as_float(r["charge_energy_used"]),
                cost=_as_float(r["cost"]),
                geofence_id=int(r["geofence_id"]) if r["geofence_id"] is not None else None,
                geofence_name=r["geofence_name"],
                lat=_as_float(r["lat"]),
                lon=_as_float(r["lon"]),
                car_id=int(r["car_id"]) if r["car_id"] is not None else None,
                charge_type=str(r["charge_type"] or "DC"),
            )
        )
    return out


def update_cost(conn: psycopg.Connection, process_id: int, cost: float) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE charging_processes SET cost = %s WHERE id = %s",
            (Decimal(f"{cost:.2f}"), process_id),
        )


def _as_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    raise TypeError(f"expected datetime, got {type(value)}")


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
