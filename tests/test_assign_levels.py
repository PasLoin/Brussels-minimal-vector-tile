import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import assign_levels as al
import osm_levels as ol


@pytest.mark.parametrize("props,expected,source", [
    ({"level": "1"}, {"level_min": 1, "level_max": 1}, "level"),
    ({"level": "0;-1"}, {"level_min": -1, "level_max": 0}, "level"),
    ({"level": "1;2;3"}, {"level_min": 1, "level_max": 3}, "level"),
    ({"level": "0.5"}, {"level_min": 0.5, "level_max": 0.5}, "level"),
    ({"level": "0", "repeat_on": "2"}, {"level_min": 0, "level_max": 2}, "level"),
    ({"location": "underground"}, {"level_min": -1, "level_max": -1, "level_approx": "yes"}, "underground"),
    ({"layer": "-2", "tunnel": "yes"}, {"level_min": -2, "level_max": -2, "level_approx": "yes"}, "underground"),
    ({"location": "roof"}, {"level_hint": "roof"}, "roof"),
    ({"location": "rooftop"}, {"level_hint": "roof"}, "roof"),
    ({"level": "2", "location": "roof"}, {"level_min": 2, "level_max": 2}, "level"),
    ({"location": "outdoor"}, {}, "default"),
    ({"level": "rez"}, {}, "default"),
    ({}, {}, "default"),
])
def test_level_props(props, expected, source):
    assert al.level_props(props) == (expected, source)


def test_underground_level():
    assert ol.underground_level({"location": "underground"}) == -1.0
    assert ol.underground_level({"location": "underground", "layer": "-3"}) == -3.0
    assert ol.underground_level({"layer": "-1"}) is None
    assert ol.underground_level({"location": "underground", "layer": "x"}) == -1.0
    assert ol.underground_level({"location": "outdoor"}) is None


def test_assign_file_is_idempotent(tmp_path):
    path = tmp_path / "poi.json"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [4.35, 50.85]},
         "properties": {"shop": "clothes", "level": "1"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [4.35, 50.85]},
         "properties": {"shop": "bakery"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [4.35, 50.85]},
         "properties": {"amenity": "vending_machine", "location": "underground"}},
    ]}))
    stats = al.assign_file(path)
    assert dict(stats) == {"level": 1, "default": 1, "underground": 1}
    first = path.read_text()
    al.assign_file(path)
    assert path.read_text() == first
    props = [f["properties"] for f in json.loads(first)["features"]]
    assert props[0]["level_min"] == 1 and props[0]["level_max"] == 1
    assert "level_min" not in props[1]
    assert props[2]["level_approx"] == "yes"


def test_poi_granulometry_keeps_level_props():
    import build_map
    for key in ("level", "level_min", "level_max", "level_approx", "level_hint"):
        assert key in build_map.POI_PROPS
