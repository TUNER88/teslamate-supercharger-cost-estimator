from datetime import datetime
from zoneinfo import ZoneInfo

from suc_estimator.db import ChargingSession
from suc_estimator.estimator import estimate_session
from suc_estimator.pricing import PriceWindow, Station


def _flat_station():
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


def _tou_station():
    # Night 00:00-08:00, day 08:00-24:00 (Europe/Berlin local)
    return Station(
        id="aachen",
        name="Aachen Supercharger",
        country="DE",
        lat=50.77,
        lon=6.08,
        timezone="Europe/Berlin",
        currency="EUR",
        windows=(
            PriceWindow(days=127, start_minute=0, end_minute=480, price_micro=260_000),
            PriceWindow(days=127, start_minute=480, end_minute=1440, price_micro=420_000),
        ),
        pricing_unit="kwh",
    )


def test_estimate_ok():
    session = ChargingSession(
        id=1,
        start_date=datetime(2026, 9, 21, 10, 0, tzinfo=ZoneInfo("UTC")),
        end_date=datetime(2026, 9, 21, 11, 0, tzinfo=ZoneInfo("UTC")),
        charge_energy_added=20.0,
        charge_energy_used=21.0,
        cost=None,
        geofence_id=1,
        geofence_name="Berlin Supercharger",
        lat=52.5201,
        lon=13.405,
    )
    result = estimate_session(session, [_flat_station()], match_radius_m=400)
    assert result.status == "ok"
    assert result.cost == 10.5  # 21 kWh * 0.5


def test_estimate_unmatched():
    session = ChargingSession(
        id=2,
        start_date=datetime(2026, 9, 21, 10, 0, tzinfo=ZoneInfo("UTC")),
        end_date=None,
        charge_energy_added=10.0,
        charge_energy_used=None,
        cost=None,
        geofence_id=None,
        geofence_name=None,
        lat=48.1,
        lon=11.5,
    )
    result = estimate_session(session, [_flat_station()], match_radius_m=400)
    assert result.status == "unmatched"


def test_cross_tou_skipped_by_default():
    # 07:00–09:00 Europe/Berlin on a Monday → crosses 08:00 boundary
    session = ChargingSession(
        id=3,
        start_date=datetime(2026, 9, 21, 5, 0, tzinfo=ZoneInfo("UTC")),  # 07:00 CEST
        end_date=datetime(2026, 9, 21, 7, 0, tzinfo=ZoneInfo("UTC")),  # 09:00 CEST
        charge_energy_added=30.0,
        charge_energy_used=30.0,
        cost=None,
        geofence_id=1,
        geofence_name="Aachen Supercharger",
        lat=50.7701,
        lon=6.0801,
    )
    result = estimate_session(session, [_tou_station()], match_radius_m=400)
    assert result.status == "skip"
    assert "time-of-use" in result.detail


def test_cross_tou_allowed_uses_start_rate():
    session = ChargingSession(
        id=4,
        start_date=datetime(2026, 9, 21, 5, 0, tzinfo=ZoneInfo("UTC")),  # 07:00 CEST night
        end_date=datetime(2026, 9, 21, 7, 0, tzinfo=ZoneInfo("UTC")),  # 09:00 CEST day
        charge_energy_added=30.0,
        charge_energy_used=30.0,
        cost=None,
        geofence_id=1,
        geofence_name="Aachen Supercharger",
        lat=50.7701,
        lon=6.0801,
    )
    result = estimate_session(
        session, [_tou_station()], match_radius_m=400, allow_cross_tou=True
    )
    assert result.status == "ok"
    assert result.cost == 7.8  # 30 kWh * 0.26 start rate
