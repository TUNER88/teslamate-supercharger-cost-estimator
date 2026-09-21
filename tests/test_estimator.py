from datetime import datetime
from zoneinfo import ZoneInfo

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
    result = estimate_session(session, [_station()], match_radius_m=400)
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
    result = estimate_session(session, [_station()], match_radius_m=400)
    assert result.status == "unmatched"
