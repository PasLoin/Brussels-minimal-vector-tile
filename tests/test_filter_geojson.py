import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import filter_geojson as fg


def feat(osm_type, osm_id, geom_type, coords, **tags):
    return {"type": "Feature",
            "geometry": {"type": geom_type, "coordinates": coords},
            "properties": {"@type": osm_type, "@id": osm_id, **tags}}


SQUARE = [[[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]]
RING = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
LINE = [[0, 0], [2, 0]]


def run(features, layer, *filters):
    kept, stats = fg.filter_features(features, [fg.parse_filter(f) for f in filters],
                                     fg.POLICIES[layer])
    return kept, stats


def test_parse_filter():
    assert fg.parse_filter("nwr/highway=a,b") == ({"node", "way", "relation"}, "highway", {"a", "b"})
    assert fg.parse_filter("n/entrance=*") == ({"node"}, "entrance", None)
    assert fg.parse_filter("w/building") == ({"way"}, "building", None)


def test_referenced_nodes_are_removed_from_poi():
    features = [
        feat("node", 1, "Point", [0, 0], shop="bakery"),
        feat("node", 2, "Point", [0, 0], entrance="main"),
        feat("node", 3, "Point", [0, 0], barrier="gate"),
    ]
    kept, stats = run(features, "poi", "nwr/shop=*")
    assert [f["properties"]["@id"] for f in kept] == [1]
    assert stats["tags"] == 2


def test_object_type_restriction():
    features = [
        feat("node", 1, "Point", [0, 0], entrance="yes"),
        feat("way", 2, "LineString", LINE, entrance="yes"),
    ]
    kept, _ = run(features, "street_furniture", "n/entrance=*")
    assert [f["properties"]["@id"] for f in kept] == [1]


def test_closed_way_keeps_only_polygon_for_area_layers():
    features = [
        feat("way", 10, "LineString", RING, landuse="residential"),
        feat("way", 10, "MultiPolygon", SQUARE, landuse="residential"),
        feat("node", 11, "Point", [0, 0], landuse="residential"),
    ]
    kept, _ = run(features, "landuse", "nwr/landuse=residential")
    assert [f["geometry"]["type"] for f in kept] == ["MultiPolygon"]


def test_hedge_prefers_line_but_keeps_area_only_hedges():
    features = [
        feat("way", 1, "LineString", RING, barrier="hedge"),
        feat("way", 1, "MultiPolygon", SQUARE, barrier="hedge"),
        feat("relation", 2, "MultiPolygon", SQUARE, barrier="hedge"),
    ]
    kept, stats = run(features, "trees", "nwr/barrier=hedge")
    assert [(f["properties"]["@id"], f["geometry"]["type"]) for f in kept] == \
        [(1, "LineString"), (2, "MultiPolygon")]
    assert stats["duplicate"] == 1


def test_bridge_area_prefers_polygon_and_roads_drop_highway_areas():
    features = [
        feat("way", 1, "LineString", RING, man_made="bridge"),
        feat("way", 1, "MultiPolygon", SQUARE, man_made="bridge"),
        feat("way", 2, "LineString", RING, highway="service"),
        feat("way", 2, "MultiPolygon", SQUARE, highway="service"),
        feat("node", 3, "Point", [0, 0], highway="crossing"),
    ]
    kept, _ = run(features, "roads", "nwr/highway=service", "nwr/man_made=bridge")
    assert [(f["properties"]["@id"], f["geometry"]["type"]) for f in kept] == \
        [(1, "MultiPolygon"), (2, "LineString")]


def test_street_furniture_ways_become_single_points():
    features = [
        feat("way", 1, "LineString", LINE, amenity="bench"),
        feat("way", 2, "LineString", RING, amenity="bench"),
        feat("way", 2, "MultiPolygon", SQUARE, amenity="bench"),
        feat("way", 3, "LineString", LINE, barrier="fence"),
        feat("node", 4, "Point", [5, 5], barrier="bollard"),
    ]
    kept, stats = run(features, "street_furniture",
                      "nwr/amenity=bench", "nwr/barrier=fence,bollard")
    by_id = {f["properties"]["@id"]: f["geometry"] for f in kept}
    assert len(kept) == 4
    assert by_id[1] == {"type": "Point", "coordinates": (1.0, 0.0)}
    assert by_id[2]["type"] == "Point"
    assert by_id[3]["type"] == "LineString"
    assert by_id[4]["coordinates"] == [5, 5]
    assert stats["converted"] == 2


def test_attributes_are_stripped(tmp_path):
    path = tmp_path / "landuse.json"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        feat("way", 1, "MultiPolygon", SQUARE, landuse="retail")]}))
    subprocess.run([sys.executable, str(ROOT / "filter_geojson.py"), str(path),
                    "--layer", "landuse", "--filters", "nwr/landuse=retail"],
                   check=True, capture_output=True)
    props = json.loads(path.read_text())["features"][0]["properties"]
    assert props == {"landuse": "retail"}


def test_street_furniture_filters_come_from_config():
    script = ('source <(sed -n "/^config_filters() {/,/^}/p" generate_json.bash); '
              'config_filters street_furniture "fallback"')
    out = subprocess.run(["bash", "-c", script], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout.split()
    import yaml
    st = yaml.safe_load((ROOT / "map.config.yaml").read_text())["layers"]["street_furniture"]["subtypes"]
    assert "n/entrance=*" in out
    flat = " ".join(out)
    for value, scfg in st.items():
        if scfg["tag"] != value:
            assert value in flat, value


def test_config_filters_fallback_without_subtypes():
    script = ('source <(sed -n "/^config_filters() {/,/^}/p" generate_json.bash); '
              'config_filters layer_inexistant "nwr/a=b n/c=*"')
    out = subprocess.run(["bash", "-c", script], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout.split()
    assert out == ["nwr/a=b", "n/c=*"]
