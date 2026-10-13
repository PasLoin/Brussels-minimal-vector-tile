import json
import subprocess
import sys
from pathlib import Path

import pytest
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import extract_indoor as ei

LINE = {"type": "LineString", "coordinates": [[4.35, 50.85], [4.3505, 50.85]]}
SQUARE = {"type": "Polygon", "coordinates": [[[4.35, 50.85], [4.3503, 50.85], [4.3503, 50.8502],
                                               [4.35, 50.8502], [4.35, 50.85]]]}
POINT = {"type": "Point", "coordinates": [4.35, 50.85]}


def feat(geometry, osm_id, osm_type="way", **tags):
    return {"type": "Feature", "geometry": geometry,
            "properties": {"@id": osm_id, "@type": osm_type, **tags}}


@pytest.mark.parametrize("raw,expected", [
    ("-1", [-1.0]),
    ("-1;0", [-1.0, 0.0]),
    ("0-2", [0.0, 1.0, 2.0]),
    ("-1--3", [-3.0, -2.0, -1.0]),
    ("-0.5;0", [-0.5, 0.0]),
    ("abc", []),
])
def test_parse_level_values(raw, expected):
    assert ei.parse_level_values(raw) == expected


def test_repeat_on_is_merged():
    assert ei.parse_level_values("0", "2;3") == [0.0, 2.0, 3.0]


@pytest.mark.parametrize("tags,kind", [
    ({"highway": "elevator"}, "elevator"),
    ({"indoor": "wall"}, "wall"),
    ({"railway": "platform"}, "platform"),
    ({"public_transport": "platform", "highway": "footway"}, "platform"),
    ({"highway": "steps", "indoor": "yes"}, "steps"),
    ({"highway": "footway"}, "footway"),
    ({"indoor": "room"}, "room"),
    ({"indoor": "yes"}, None),
    ({"indoor": "door"}, None),
])
def test_classify(tags, kind):
    assert ei.classify(tags) == kind


def test_levels_from_tag_or_underground_hint():
    assert ei.resolve_levels({"level": "-2"}, "footway") == ([-2.0], False)
    assert ei.resolve_levels({"layer": "-1", "tunnel": "yes"}, "footway") == ([-1.0], True)
    assert ei.resolve_levels({"layer": "-1"}, "footway") == (None, False)
    assert ei.resolve_levels({"layer": "-1", "tunnel": "building_passage"}, "footway") == (None, False)
    assert ei.resolve_levels({}, "footway") == (None, False)
    assert ei.resolve_levels({"indoor": "room"}, "room") == ([0.0], True)


def test_outdoor_platform_without_level_is_skipped():
    built, _ = ei.build_feature("platform", feat(SQUARE, 1, railway="platform"))
    assert built is None


def test_line_is_buffered_to_polygon_of_expected_width():
    built, levels = ei.build_feature("steps", feat(LINE, 2, highway="steps", level="-1;0"))
    geom = shape(built["geometry"])
    assert geom.geom_type == "Polygon"
    assert levels == [-1.0, 0.0]
    assert built["properties"]["level_min"] == -1.0
    assert built["properties"]["level_max"] == 0.0
    scale = ei.metric_scale(geom)
    area_m2 = geom.area * scale[0] * scale[1]
    length_m = 0.0005 * scale[0]
    assert area_m2 == pytest.approx(length_m * ei.LINE_WIDTHS["steps"], rel=0.05)


def test_elevator_node_becomes_square_column():
    built, _ = ei.build_feature("elevator", feat(POINT, 3, "node", highway="elevator", level="-2;0"))
    geom = shape(built["geometry"])
    scale = ei.metric_scale(geom)
    assert geom.area * scale[0] * scale[1] == pytest.approx(1.8 ** 2, rel=0.05)
    assert (built["properties"]["level_min"], built["properties"]["level_max"]) == (-2.0, 0.0)


def test_closed_way_keeps_area_for_rooms_and_line_for_walls():
    room_line = feat({"type": "LineString", "coordinates": SQUARE["coordinates"][0]}, 10, indoor="room", level="1")
    room_area = feat(SQUARE, 10, indoor="room", level="1")
    wall_line = feat({"type": "LineString", "coordinates": SQUARE["coordinates"][0]}, 11, indoor="wall", level="1")
    wall_area = feat(SQUARE, 11, indoor="wall", level="1")
    selected = {f["properties"]["@id"]: (kind, f["geometry"]["type"])
                for kind, f in ei.select_features([room_line, room_area, wall_area, wall_line])}
    assert selected[10] == ("room", "Polygon")
    assert selected[11] == ("wall", "LineString")


def test_cli_writes_layer_and_levels(tmp_path):
    src = tmp_path / "in.json"
    src.write_text(json.dumps({"type": "FeatureCollection", "features": [
        feat(LINE, 1, highway="footway", level="-2"),
        feat(LINE, 2, highway="footway"),
        feat(SQUARE, 3, railway="platform", level="-1"),
        feat(POINT, 4, "node", highway="elevator", level="-2;0"),
    ]}))
    out = tmp_path / "indoor.json"
    levels = tmp_path / "levels.json"
    subprocess.run([sys.executable, "extract_indoor.py", "--input", src, "--output", out,
                    "--levels-out", levels], cwd=ROOT, check=True, capture_output=True)
    features = json.loads(out.read_text())["features"]
    assert sorted(f["properties"]["kind"] for f in features) == ["elevator", "footway", "platform"]
    assert all("@id" not in f["properties"] for f in features)
    doc = json.loads(levels.read_text())
    assert [l["level"] for l in doc["levels"]] == [-2, -1, 0]
