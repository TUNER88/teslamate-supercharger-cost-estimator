from datetime import datetime
from zoneinfo import ZoneInfo

from suc_estimator.pricing import (
    PriceWindow,
    load_stations,
    micro_to_currency,
    rate_at,
    select_window,
    weekday_bit,
)


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
