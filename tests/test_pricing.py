from datetime import datetime
from zoneinfo import ZoneInfo

from suc_estimator.pricing import (
    MinuteTier,
    MinuteWindow,
    PriceWindow,
    load_stations,
    micro_to_currency,
    parse_station,
    rate_at,
    select_window,
    tier_for_power,
    weekday_bit,
)


def _minute_station_raw():
    return {
        "id": "innsbruck",
        "name": "Innsbruck, Austria",
        "country": "AT",
        "lat": 47.27,
        "lon": 11.4,
        "timezone": "Europe/Vienna",
        "pricing": {
            "tesla": {
                "currency": "EUR",
                "pricingStatus": "available",
                "pricingUnit": "minute",
                "prices": [],
                "minutePrices": [
                    {
                        "days": 127,
                        "start": 0,
                        "end": 1440,
                        "tiers": [
                            {"minPowerKw": 0, "maxPowerKw": 60, "price": 170000},
                            {"minPowerKw": 60, "maxPowerKw": 100, "price": 350000},
                            {"minPowerKw": 100, "maxPowerKw": 180, "price": 540000},
                            {"minPowerKw": 180, "maxPowerKw": None, "price": 900000},
                        ],
                    }
                ],
            }
        },
    }


def test_micro_to_currency():
    assert micro_to_currency(260_000) == 0.26
    assert micro_to_currency(420_000) == 0.42


def test_weekday_bit_monday():
    dt = datetime(2026, 9, 21, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))  # Monday
    assert weekday_bit(dt) == 1


def test_select_window_tou():
    windows = (
        PriceWindow(days=127, start_minute=0, end_minute=480, price_micro=260_000),
        PriceWindow(days=127, start_minute=480, end_minute=1200, price_micro=420_000),
        PriceWindow(days=127, start_minute=1200, end_minute=1440, price_micro=380_000),
    )
    morning = datetime(2026, 9, 21, 7, 30, tzinfo=ZoneInfo("Europe/Berlin"))
    midday = datetime(2026, 9, 21, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    evening = datetime(2026, 9, 21, 21, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    assert select_window(windows, morning).price_micro == 260_000
    assert select_window(windows, midday).price_micro == 420_000
    assert select_window(windows, evening).price_micro == 380_000


def test_load_stations_from_sample():
    payload = {
        "stations": [
            {
                "id": "aachen",
                "name": "Aachen, Germany",
                "country": "DE",
                "lat": 50.77,
                "lon": 6.08,
                "timezone": "Europe/Berlin",
                "pricing": {
                    "tesla": {
                        "currency": "EUR",
                        "pricingStatus": "available",
                        "pricingUnit": "kwh",
                        "prices": [
                            {"days": 127, "start": 0, "end": 1440, "price": 400000},
                        ],
                    }
                },
            }
        ]
    }
    stations = load_stations(payload, family="tesla")
    assert len(stations) == 1
    assert stations[0].currency == "EUR"
    w = rate_at(stations[0], datetime(2026, 9, 21, 10, 0, tzinfo=ZoneInfo("UTC")))
    assert w is not None
    assert micro_to_currency(w.price_micro) == 0.4


def test_parse_minute_station():
    station = parse_station(_minute_station_raw())
    assert station is not None
    assert station.pricing_unit == "minute"
    assert station.windows == ()
    assert len(station.minute_windows) == 1
    window = station.minute_windows[0]
    assert isinstance(window, MinuteWindow)
    assert len(window.tiers) == 4
    assert window.tiers[0] == MinuteTier(0.0, 60.0, 170_000)
    assert window.tiers[-1].max_power_kw is None


def test_parse_minute_station_missing_tiers():
    raw = _minute_station_raw()
    raw["pricing"]["tesla"]["minutePrices"] = [
        {"days": 127, "start": 0, "end": 1440, "tiers": []}
    ]
    assert parse_station(raw) is None


def test_parse_minute_station_skips_bad_tier():
    raw = _minute_station_raw()
    raw["pricing"]["tesla"]["minutePrices"][0]["tiers"] = [
        {"minPowerKw": 0, "maxPowerKw": 60, "price": "not-a-number"},
        {"minPowerKw": 60, "maxPowerKw": 100, "price": 350000},
    ]
    station = parse_station(raw)
    assert station is not None
    assert len(station.minute_windows[0].tiers) == 1


def test_minute_window_rates_by_time():
    station = parse_station(_minute_station_raw())
    # Innsbruck local time = UTC+2 in September
    day = datetime(2026, 9, 21, 8, 0, tzinfo=ZoneInfo("UTC"))
    window = rate_at(station, day)
    assert isinstance(window, MinuteWindow)
    assert window.start_minute == 0
    assert window.end_minute == 1440


def test_tier_for_power_bounds():
    tiers = (
        MinuteTier(0.0, 60.0, 170_000),
        MinuteTier(60.0, 100.0, 350_000),
        MinuteTier(100.0, 180.0, 540_000),
        MinuteTier(180.0, None, 900_000),
    )
    assert tier_for_power(tiers, 0).price_micro == 170_000
    assert tier_for_power(tiers, 59.9).price_micro == 170_000
    assert tier_for_power(tiers, 60.0).price_micro == 350_000  # boundary -> next tier
    assert tier_for_power(tiers, 99.99).price_micro == 350_000
    assert tier_for_power(tiers, 180.0).price_micro == 900_000  # open-ended
    assert tier_for_power(tiers, 500.0).price_micro == 900_000
    # no tier below min power
    assert tier_for_power((MinuteTier(60.0, 100.0, 1),), 10) is None


def _minute_tiers():
    return (
        MinuteTier(0.0, 60.0, 170_000),
        MinuteTier(60.0, 100.0, 350_000),
        MinuteTier(100.0, 180.0, 540_000),
        MinuteTier(180.0, None, 900_000),
    )


def test_tier_for_power_half_open_bounds():
    """A tier holds [min, max); the next tier starts exactly at max."""
    tiers = _minute_tiers()
    assert tier_for_power(tiers, 0.0).price_micro == 170_000
    assert tier_for_power(tiers, 60.0).price_micro == 350_000
    assert tier_for_power(tiers, 100.0).price_micro == 540_000
    assert tier_for_power(tiers, 180.0).price_micro == 900_000
    assert tier_for_power(tiers, 60.0001).price_micro == 350_000


def test_kwh_station_preferred_over_minute():
    # A block declaring kwh with BOTH price kinds parses both, but the
    # declared unit decides which one is used for estimation.
    raw = _minute_station_raw()
    raw["pricing"]["tesla"]["pricingUnit"] = "kwh"
    raw["pricing"]["tesla"]["prices"] = [
        {"days": 127, "start": 0, "end": 1440, "price": 400000}
    ]
    station = parse_station(raw)
    assert station is not None
    assert station.pricing_unit == "kwh"
    assert station.windows
    assert station.minute_windows  # parsed too, but unused while unit is kwh


def test_station_without_pricing_block():
    assert parse_station({"id": "x", "lat": 0.0, "lon": 0.0}) is None