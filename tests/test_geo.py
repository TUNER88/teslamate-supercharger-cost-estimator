from dataclasses import dataclass

from suc_estimator.geo import haversine_m, nearest


@dataclass
class P:
    lat: float
    lon: float
    name: str


def test_haversine_same_point():
    assert haversine_m(52.5, 13.4, 52.5, 13.4) < 1


def test_nearest_within_radius():
    items = [
        P(52.5200, 13.4050, "near"),
        P(48.1371, 11.5754, "far"),
    ]
    hit = nearest(52.5201, 13.4051, items, lambda p: (p.lat, p.lon), 500)
    assert hit is not None
    assert hit[0].name == "near"
    assert hit[1] < 50


def test_nearest_outside_radius():
    items = [P(48.1371, 11.5754, "munich")]
    assert nearest(52.52, 13.40, items, lambda p: (p.lat, p.lon), 500) is None
