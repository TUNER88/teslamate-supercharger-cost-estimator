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


def test_ac_session_skipped_before_geo_match():
    """AC sessions are skipped without attempting Supercharger geo-match."""
    session = ChargingSession(
        id=100,
        start_date=datetime(2026, 9, 21, 10, 0, tzinfo=ZoneInfo("UTC")),
        end_date=datetime(2026, 9, 21, 11, 0, tzinfo=ZoneInfo("UTC")),
        charge_energy_added=20.0,
        charge_energy_used=21.0,
        cost=None,
        geofence_id=1,
        geofence_name="Home",
        lat=52.5201,  # would match Berlin SuC if geo-matched
        lon=13.405,
        charge_type="AC",
    )
    result = estimate_session(session, [_flat_station()], match_radius_m=400)
    assert result.status == "skip"
    assert result.detail == "AC (charger_phases)"
    assert result.station_id is None
    assert result.cost is None


def test_dc_session_still_geo_matched():
    """DC (phases null/0) keeps current matching behaviour."""
    session = ChargingSession(
        id=101,
        start_date=datetime(2026, 9, 21, 10, 0, tzinfo=ZoneInfo("UTC")),
        end_date=datetime(2026, 9, 21, 11, 0, tzinfo=ZoneInfo("UTC")),
        charge_energy_added=20.0,
        charge_energy_used=21.0,
        cost=None,
        geofence_id=1,
        geofence_name="Berlin Supercharger",
        lat=52.5201,
        lon=13.405,
        charge_type="DC",
    )
    result = estimate_session(session, [_flat_station()], match_radius_m=400)
    assert result.status == "ok"
    assert result.cost == 10.5


def test_missing_charge_samples_treated_as_dc():
    """Default charge_type is DC so sparse SuC sessions still attempt match."""
    session = ChargingSession(
        id=102,
        start_date=datetime(2026, 9, 21, 10, 0, tzinfo=ZoneInfo("UTC")),
        end_date=datetime(2026, 9, 21, 11, 0, tzinfo=ZoneInfo("UTC")),
        charge_energy_added=20.0,
        charge_energy_used=21.0,
        cost=None,
        geofence_id=1,
        geofence_name="Berlin Supercharger",
        lat=52.5201,
        lon=13.405,
        # charge_type omitted → default "DC"
    )
    assert session.charge_type == "DC"
    result = estimate_session(session, [_flat_station()], match_radius_m=400)
    assert result.status == "ok"
