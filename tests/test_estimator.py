from datetime import datetime
from zoneinfo import ZoneInfo

from suc_estimator.db import ChargingSession
from suc_estimator.estimator import estimate_session, looks_like_supercharger
from suc_estimator.pricing import (
    MinuteTier,
    MinuteWindow,
    PriceWindow,
    Station,
)


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


MINUTE_STATION = Station(
    id="innsbruck",
    name="Innsbruck Supercharger",
    country="AT",
    lat=47.27,
    lon=11.4,
    timezone="Europe/Vienna",
    currency="EUR",
    windows=(),
    pricing_unit="minute",
    minute_windows=(
        MinuteWindow(
            days=127,
            start_minute=0,
            end_minute=1440,
            tiers=(
                MinuteTier(0.0, 60.0, 170_000),
                MinuteTier(60.0, 100.0, 350_000),
                MinuteTier(100.0, 180.0, 540_000),
                MinuteTier(180.0, None, 900_000),
            ),
        ),
    ),
)


def _minute_session(**overrides):
    base = {
        "id": 10,
        "start_date": datetime(2026, 9, 21, 8, 0, tzinfo=ZoneInfo("UTC")),
        "end_date": datetime(2026, 9, 21, 9, 0, tzinfo=ZoneInfo("UTC")),
        "charge_energy_added": 56.0,
        "charge_energy_used": 60.0,
        "cost": None,
        "geofence_id": 3,
        "geofence_name": "Innsbruck Supercharger",
        "lat": 47.2701,
        "lon": 11.4001,
        "car_id": 1,
    }
    base.update(overrides)
    return ChargingSession(**base)


def test_minute_station_estimate_tier_by_avg_power():
    # 60 kWh over 60 min -> 60 kW average -> 0.35/min tier
    result = estimate_session(_minute_session(), [MINUTE_STATION], match_radius_m=400)
    assert result.status == "ok"
    assert result.station_id == "innsbruck"
    assert result.rate_per_kwh == 0.35
    assert result.cost == 21.0  # 60 min * 0.35
    assert "/min" in result.detail


def test_minute_station_low_power_tier():
    session = _minute_session(charge_energy_added=30.0, charge_energy_used=30.0)
    result = estimate_session(session, [MINUTE_STATION], match_radius_m=400)
    assert result.status == "ok"
    # 30 kWh over 60 min -> 30 kW avg -> 0.17/min tier
    assert result.rate_per_kwh == 0.17
    assert result.cost == 10.2  # 60 min * 0.17


def test_minute_station_open_ended_tier():
    session = _minute_session(charge_energy_added=250.0, charge_energy_used=250.0)
    result = estimate_session(session, [MINUTE_STATION], match_radius_m=400)
    assert result.status == "ok"
    # 250 kWh over 60 min -> 250 kW avg -> open tier 0.90/min
    assert result.rate_per_kwh == 0.90
    assert result.cost == 54.0


def test_minute_station_short_session_uses_minutes():
    session = _minute_session(
        start_date=datetime(2026, 9, 21, 8, 0, tzinfo=ZoneInfo("UTC")),
        end_date=datetime(2026, 9, 21, 8, 30, tzinfo=ZoneInfo("UTC")),
        charge_energy_added=15.0,
        charge_energy_used=15.0,
    )
    result = estimate_session(session, [MINUTE_STATION], match_radius_m=400)
    assert result.status == "ok"
    # 15 kWh over 30 min -> 30 kW avg -> 0.17/min * 30 min
    assert result.cost == 5.1


def test_minute_station_without_end_skips():
    session = _minute_session(end_date=None)
    result = estimate_session(session, [MINUTE_STATION], match_radius_m=400)
    assert result.status == "skip"
    assert "end time" in result.detail


def test_minute_station_zero_duration_skips():
    session = _minute_session(
        start_date=datetime(2026, 9, 21, 8, 0, tzinfo=ZoneInfo("UTC")),
        end_date=datetime(2026, 9, 21, 8, 0, tzinfo=ZoneInfo("UTC")),
    )
    result = estimate_session(session, [MINUTE_STATION], match_radius_m=400)
    assert result.status == "skip"
    assert "duration" in result.detail


def test_minute_station_estimate_avg_power_lands_in_bracket():
    # 15 kWh over 15 min -> 60 kW avg -> exactly the 60-100 bracket boundary
    session = _minute_session(
        start_date=datetime(2026, 9, 21, 8, 0, tzinfo=ZoneInfo("UTC")),
        end_date=datetime(2026, 9, 21, 8, 15, tzinfo=ZoneInfo("UTC")),
        charge_energy_added=15.0,
        charge_energy_used=15.0,
    )
    result = estimate_session(session, [MINUTE_STATION], match_radius_m=400)
    assert result.status == "ok"
    assert result.rate_per_kwh == 0.35
    assert result.cost == 5.25  # 15 min * 0.35


def test_minute_station_still_matches_over_kwh_station():
    # The minute-priced station is the nearest one (session is on top of it):
    # it must win over a slightly farther kWh-priced station. Before minute
    # stations were parsed, this session would have latched on to the kWh
    # station and been billed at its rate.
    kwh = Station(
        id="kwh-nearby",
        name="Somewhere kWh",
        country="AT",
        lat=47.2712,   # ~120 m north of the session: farther than the minute
        lon=11.4000,   # station (~11 m), still inside the 400 m match radius
        timezone="Europe/Vienna",
        currency="EUR",
        windows=(PriceWindow(days=127, start_minute=0, end_minute=1440, price_micro=400_000),),
        pricing_unit="kwh",
    )
    result = estimate_session(_minute_session(), [kwh, MINUTE_STATION], match_radius_m=400)
    assert result.status == "ok"
    assert result.station_id == "innsbruck"


def test_looks_like_supercharger():
    assert looks_like_supercharger(_minute_session()) is True
    home = _minute_session(geofence_name="Home Garage", geofence_id=None)
    assert looks_like_supercharger(home) is False
    none_name = _minute_session(geofence_name=None)
    assert looks_like_supercharger(none_name) is False


def _tou_minute_station():
    """Per-minute station with a night window (00:00-08:00) and day window."""
    return Station(
        id="tou-minute",
        name="TOU Minute Supercharger",
        country="AT",
        lat=47.27,
        lon=11.4,
        timezone="Europe/Vienna",
        currency="EUR",
        windows=(),
        pricing_unit="minute",
        minute_windows=(
            MinuteWindow(
                days=127,
                start_minute=0,
                end_minute=480,
                tiers=(MinuteTier(0.0, 60.0, 170_000),),
            ),
            MinuteWindow(
                days=127,
                start_minute=480,
                end_minute=1440,
                tiers=(MinuteTier(0.0, 60.0, 350_000),),
            ),
        ),
    )


def test_minute_cross_tou_skipped_by_default():
    # 05:00-09:00 UTC = 07:00-11:00 Vienna: crosses the 08:00 window boundary
    session = _minute_session(
        start_date=datetime(2026, 9, 21, 5, 0, tzinfo=ZoneInfo("UTC")),
        end_date=datetime(2026, 9, 21, 9, 0, tzinfo=ZoneInfo("UTC")),
        charge_energy_added=30.0,
        charge_energy_used=30.0,
    )
    result = estimate_session(session, [_tou_minute_station()], match_radius_m=400)
    assert result.status == "skip"
    assert "time-of-use" in result.detail


def test_minute_cross_tou_allowed_uses_start_window():
    session = _minute_session(
        start_date=datetime(2026, 9, 21, 5, 0, tzinfo=ZoneInfo("UTC")),
        end_date=datetime(2026, 9, 21, 9, 0, tzinfo=ZoneInfo("UTC")),
        charge_energy_added=30.0,
        charge_energy_used=30.0,
    )
    result = estimate_session(
        session, [_tou_minute_station()], match_radius_m=400, allow_cross_tou=True
    )
    assert result.status == "ok"
    # 4h session at 30 kWh -> 7.5 kW avg -> night tier 0.17/min; 240 min * 0.17
    assert result.cost == 40.8
