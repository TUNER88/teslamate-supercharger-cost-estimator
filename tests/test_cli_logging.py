"""CLI logging helpers: unmatched once, quiet no-op passes."""

from __future__ import annotations

import logging
from argparse import Namespace
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from suc_estimator.cli import LoopState, PassOutcome, run_once
from suc_estimator.db import ChargingSession
from suc_estimator.estimator import estimate_session
from suc_estimator.pricing import PriceWindow, Station


def _station():
    return Station(
        id="berlin",
        name="Berlin Supercharger",
        country="DE",
        lat=52.52,
        lon=13.40,
        timezone="Europe/Berlin",
        currency="EUR",
        windows=(PriceWindow(days=127, start_minute=0, end_minute=1440, price_micro=500_000),),
        pricing_unit="kwh",
    )


def _session(**overrides):
    base = {
        "id": 1,
        "start_date": datetime(2026, 9, 21, 10, 0, tzinfo=ZoneInfo("UTC")),
        "end_date": datetime(2026, 9, 21, 11, 0, tzinfo=ZoneInfo("UTC")),
        "charge_energy_added": 20.0,
        "charge_energy_used": 21.0,
        "cost": None,
        "geofence_id": 1,
        "geofence_name": "Berlin Supercharger",
        "lat": 52.5201,
        "lon": 13.405,
        "car_id": 1,
    }
    base.update(overrides)
    return ChargingSession(**base)


def _args(**overrides) -> Namespace:
    base = dict(
        dry_run=True,
        lookback_days=90,
        match_radius_m=400.0,
        overwrite=False,
        pricing_family="tesla",
        price_url="https://example.test/europe.json",
        cache_dir="/tmp/suc-cache-test",
        cache_ttl=43200,
        allow_cross_tou=False,
        update_interval_seconds=0,
        verbose=False,
    )
    base.update(overrides)
    return Namespace(**base)


def test_unmatched_detail_includes_nearest_station():
    session = _session(id=99, lat=48.1, lon=11.5, geofence_name="Munich area")
    result = estimate_session(session, [_station()], match_radius_m=400)
    assert result.status == "unmatched"
    assert "Berlin Supercharger" in result.detail
    assert "nearest:" in result.detail
    assert "m)" in result.detail


def _run_pass(sessions, state: LoopState, caplog, **arg_overrides):
    args = _args(**arg_overrides)
    payload = {"stations": []}
    stations = [_station()]
    conn = MagicMock()
    with (
        patch("suc_estimator.cli.fetch_prices", return_value=payload),
        patch("suc_estimator.cli.load_stations", return_value=stations),
        patch("suc_estimator.cli.connect") as connect_mock,
        patch("suc_estimator.cli.fetch_sessions", return_value=sessions),
        patch("suc_estimator.cli.update_cost"),
        caplog.at_level(logging.INFO, logger="suc_estimator"),
    ):
        connect_mock.return_value.__enter__.return_value = conn
        connect_mock.return_value.__exit__.return_value = None
        rc = run_once(
            args,
            host="db",
            port=5432,
            name="teslamate",
            user="teslamate",
            password="x",
            state=state,
        )
    assert rc == 0
    return [r.getMessage() for r in caplog.records if r.name == "suc_estimator"]


def test_unmatched_logged_once_at_info(caplog):
    far = _session(id=42, lat=48.1, lon=11.5, geofence_name="Somewhere Supercharger")
    state = LoopState()

    msgs1 = _run_pass([far], state, caplog)
    unmatched_infos = [m for m in msgs1 if m.startswith("unmatched id=42")]
    assert len(unmatched_infos) == 1
    assert "Somewhere Supercharger" in unmatched_infos[0]
    assert "nearest:" in unmatched_infos[0]

    caplog.clear()
    msgs2 = _run_pass([far], state, caplog)
    unmatched_infos2 = [m for m in msgs2 if m.startswith("unmatched id=42")]
    assert unmatched_infos2 == []  # second pass: DEBUG only, not INFO


def test_quiet_noop_pass_suppresses_ritual(caplog):
    far = _session(id=42, lat=48.1, lon=11.5, geofence_name="Somewhere Supercharger")
    state = LoopState()

    msgs1 = _run_pass([far], state, caplog)
    assert any("Fetching public Supercharger rates" in m for m in msgs1)
    assert any(m.startswith("Done:") for m in msgs1)
    assert state.next_verbose is False

    caplog.clear()
    msgs2 = _run_pass([far], state, caplog)
    assert any("No changes since last pass" in m for m in msgs2)
    assert not any("Fetching public Supercharger rates" in m for m in msgs2)
    assert not any(m.startswith("Done:") for m in msgs2)


def test_pass_outcome_tracks_unmatched_ids():
    outcome = PassOutcome(0, 0, 1, 0, frozenset({42}))
    assert outcome.unmatched_ids == frozenset({42})
