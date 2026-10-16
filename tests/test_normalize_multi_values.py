import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import normalize_multi_values as nmv
import generate_poi_icons as gpi


@pytest.mark.parametrize("raw, expected", [
    ("pizza;italian", "pizza"),
    ("italian;spanish;pizza", "italian"),
    (" french ; italian", "french"),
    (";belgian;french", "belgian"),
    ("friture", "friture"),
    (";", None),
    ("  ", None),
])
def test_first_value(raw, expected):
    assert nmv.first_value(raw) == expected


def test_normalize_properties_only_touches_multi_value_keys():
    props = {"cuisine": "pizza;italian", "vending": "drinks;food",
             "religion": "christian", "name": "A;B", "door": ";"}
    assert nmv.normalize_properties(props) == 3
    assert props == {"cuisine": "pizza", "vending": "drinks",
                     "religion": "christian", "name": "A;B"}


def test_normalize_file_street_furniture(tmp_path):
    path = tmp_path / "street_furniture.json"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [4.35, 50.85]},
         "properties": {"amenity": "vending_machine", "vending": "parking_tickets;public_transport_tickets"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [4.36, 50.86]},
         "properties": {"entrance": "main", "door": "hinged"}},
    ]}))
    assert nmv.normalize_file(path) == 1
    feats = json.loads(path.read_text())["features"]
    assert feats[0]["properties"]["vending"] == "parking_tickets"
    assert feats[1]["properties"]["door"] == "hinged"
    assert nmv.normalize_file(path) == 0


def test_icon_sub_types_match_normalized_values(tmp_path):
    path = tmp_path / "poi.json"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]},
         "properties": {"amenity": "restaurant", "cuisine": ";friture;belgian"}},
    ]}))
    _, _, _, raw_sub_types = gpi.extract_poi_types([path])
    nmv.normalize_file(path)
    props = json.loads(path.read_text())["features"][0]["properties"]
    assert raw_sub_types == {"cuisine-friture": {"key": "cuisine", "value": "friture"}}
    assert props["cuisine"] == raw_sub_types["cuisine-friture"]["value"]
