#!/usr/bin/env python3
import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

from osm_levels import format_level, parse_level_values, underground_level

try:
    import numpy as np
    import shapely
    from shapely.geometry import Polygon, mapping, shape
    from shapely.ops import linemerge, substring
except ImportError:
    print("✗  pip install shapely", file=sys.stderr)
    sys.exit(1)

LINE = {"LineString", "MultiLineString"}
AREA = {"Polygon", "MultiPolygon"}
POINT = {"Point", "MultiPoint"}

LINE_WIDTHS = {
    "wall": 0.15,
    "steps": 1.5,
    "escalator": 1.2,
    "corridor": 1.5,
    "footway": 1.2,
    "pedestrian": 3.0,
    "platform": 2.5,
    "elevator": 1.8,
}
POINT_SIZES = {"elevator": 1.8, "platform": 2.0}

PREFERS_AREA = {"room", "area", "corridor", "platform", "pedestrian", "elevator"}

KEEP_PROPS = ("name", "ref", "level", "repeat_on")

SLOPED_KINDS = {"steps", "escalator"}
SLICE_LENGTH = 1.0
MIN_SLICES = 3
MAX_SLICES = 24
SLICE_PROPS = ("kind", "level_min", "level_max", "level_approx", "conveying")
ARROW_SPACING = 3.0
CONVEYING_DIRECTIONS = {"forward": (1,), "yes": (1,), "backward": (-1,), "reversible": (1, -1)}


def classify(props):
    highway = props.get("highway")
    indoor = props.get("indoor")
    if highway == "elevator":
        return "elevator"
    if indoor == "wall":
        return "wall"
    if props.get("railway") == "platform" or props.get("public_transport") == "platform":
        return "platform"
    if highway == "steps":
        if props.get("conveying") not in (None, "", "no"):
            return "escalator"
        return "steps"
    if highway == "corridor":
        return "corridor"
    if highway in ("footway", "path"):
        return "footway"
    if highway == "pedestrian":
        return "pedestrian"
    if indoor in ("room", "area", "corridor"):
        return indoor
    return None


def resolve_levels(props, kind):
    values = parse_level_values(props.get("level"), props.get("repeat_on"))
    if values:
        return values, False
    approx = underground_level(props)
    if approx is not None:
        return [approx], True
    if kind in ("room", "area", "corridor", "wall") and props.get("indoor"):
        return [0.0], True
    return None, False


def metric_scale(geom):
    lat0 = math.radians(geom.centroid.y)
    return np.array([111_320 * math.cos(lat0), 110_540.0])


def to_area(geom, kind):
    if geom.is_empty:
        return None
    if geom.geom_type in AREA:
        if not geom.is_valid:
            geom = geom.buffer(0)
        return None if geom.is_empty else geom
    scale = metric_scale(geom)
    metric = shapely.transform(geom, lambda c: c * scale)
    if geom.geom_type in POINT:
        size = POINT_SIZES.get(kind)
        if not size:
            return None
        buffered = metric.buffer(size / 2, cap_style=3, join_style=2)
    else:
        width = LINE_WIDTHS.get(kind, 1.2)
        buffered = metric.buffer(width / 2, cap_style=2, join_style=2)
    if buffered.is_empty:
        return None
    return shapely.transform(buffered, lambda c: c / scale)


def osm_key(props, index):
    t, i = props.get("@type"), props.get("@id")
    if t is None or i is None:
        return ("anon", index)
    return (t, i)


def geometry_rank(gtype, kind):
    if kind in PREFERS_AREA:
        order = (AREA, LINE, POINT)
    else:
        order = (LINE, AREA, POINT)
    for rank, group in enumerate(order):
        if gtype in group:
            return rank
    return len(order)


def select_features(features):
    best = {}
    for index, feat in enumerate(features):
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        kind = classify(props)
        if kind is None or gtype is None:
            continue
        key = osm_key(props, index)
        rank = geometry_rank(gtype, kind)
        if key not in best or rank < best[key][0]:
            best[key] = (rank, kind, feat)
    return [(kind, feat) for _, kind, feat in best.values()]


def build_feature(kind, feat):
    props = feat.get("properties") or {}
    levels, approx = resolve_levels(props, kind)
    if not levels:
        return None, None
    try:
        area = to_area(shape(feat["geometry"]), kind)
    except Exception:
        return None, None
    if area is None:
        return None, None
    out_props = {"kind": kind, "level_min": levels[0], "level_max": levels[-1]}
    for key in KEEP_PROPS:
        if props.get(key) not in (None, ""):
            out_props[key] = props[key]
    if approx:
        out_props["level_approx"] = "yes"
    return {"type": "Feature", "geometry": mapping(area), "properties": out_props}, levels


def incline_sign(value):
    if value is None:
        return 0
    text = str(value).strip().lower()
    if text == "up":
        return 1
    if text == "down":
        return -1
    try:
        number = float(text.rstrip("%°").strip())
    except ValueError:
        return 0
    return (number > 0) - (number < 0)


def vertex_key(coord):
    return (round(coord[0], 7), round(coord[1], 7))


def build_vertex_levels(features):
    index = {}
    for feat in features:
        props = feat.get("properties") or {}
        if props.get("highway") == "steps":
            continue
        levels = parse_level_values(props.get("level"), props.get("repeat_on"))
        if not levels:
            continue
        coords = []
        _collect_coords((feat.get("geometry") or {}).get("coordinates"), coords)
        for coord in coords:
            index.setdefault(vertex_key(coord), set()).update(levels)
    return index


def _collect_coords(coords, out):
    if not isinstance(coords, list) or not coords:
        return
    if isinstance(coords[0], (int, float)):
        out.append(coords)
        return
    for item in coords:
        _collect_coords(item, out)


def climbs_along_way(props, coords, lo, hi, vertex_levels):
    sign = incline_sign(props.get("incline"))
    if sign:
        return sign > 0
    start = (vertex_levels or {}).get(vertex_key(coords[0]), set())
    end = (vertex_levels or {}).get(vertex_key(coords[-1]), set())
    if (hi in start and lo not in start) or (lo in end and hi not in end):
        return False
    return True


def single_line(geom):
    if geom.geom_type == "LineString":
        return geom
    if geom.geom_type == "MultiLineString":
        merged = linemerge(geom)
        if merged.geom_type == "LineString":
            return merged
    return None


def chevron(point, tangent, half_width):
    tx, ty = tangent
    nx, ny = -ty, tx
    px, py = point
    a = half_width
    return Polygon([
        (px + tx * a, py + ty * a),
        (px - tx * a * 0.6 + nx * a, py - ty * a * 0.6 + ny * a),
        (px - tx * a * 0.1, py - ty * a * 0.1),
        (px - tx * a * 0.6 - nx * a, py - ty * a * 0.6 - ny * a),
    ])


def tangent_at(line, distance):
    length = line.length
    p0 = line.interpolate(max(0.0, distance - 0.2))
    p1 = line.interpolate(min(length, distance + 0.2))
    dx, dy = p1.x - p0.x, p1.y - p0.y
    norm = math.hypot(dx, dy) or 1.0
    return dx / norm, dy / norm


def sloped_features(kind, line, levels, base_props, climbs_forward):
    lo, hi = levels[0], levels[-1]
    scale = metric_scale(line)
    metric = shapely.transform(line, lambda c: c * scale)
    back = lambda g: mapping(shapely.transform(g, lambda c: np.round(c / scale, 7)))
    length = metric.length
    if length <= 0:
        return []
    n = max(MIN_SLICES, min(MAX_SLICES, round(length / SLICE_LENGTH)))
    width = LINE_WIDTHS.get(kind, 1.2)

    def top_at(fraction):
        rise = fraction if climbs_forward else 1.0 - fraction
        return round(lo + (hi - lo) * rise, 3)

    out = []
    for i in range(n):
        piece = substring(metric, length * i / n, length * (i + 1) / n)
        poly = piece.buffer(width / 2, cap_style=2, join_style=2)
        if poly.is_empty:
            continue
        fraction = (i + 1) / n if climbs_forward else i / n
        source = base_props if i == 0 else {k: base_props[k] for k in SLICE_PROPS if k in base_props}
        props = dict(source, z_top=top_at(fraction))
        out.append({"type": "Feature", "geometry": back(poly), "properties": props})

    directions = CONVEYING_DIRECTIONS.get(base_props.get("conveying")) if kind == "escalator" else None
    if directions:
        count = max(1, int(length // ARROW_SPACING))
        for j in range(count):
            distance = length * (j + 0.5) / count
            slice_index = min(n - 1, int(distance / length * n))
            fraction = (slice_index + 1) / n if climbs_forward else slice_index / n
            point = metric.interpolate(distance)
            tx, ty = tangent_at(metric, distance)
            for k, direction in enumerate(directions):
                shift = 0.0 if len(directions) == 1 else (0.35 if k == 0 else -0.35)
                center = (point.x + tx * shift, point.y + ty * shift)
                arrow = chevron(center, (tx * direction, ty * direction), width * 0.38)
                props = {"kind": "arrow", "level_min": lo, "level_max": hi, "z_top": top_at(fraction)}
                if base_props.get("level_approx"):
                    props["level_approx"] = "yes"
                out.append({"type": "Feature", "geometry": back(arrow), "properties": props})
    return out


def build_features(kind, feat, vertex_levels=None):
    built, levels = build_feature(kind, feat)
    if built is None or kind not in SLOPED_KINDS or levels[0] == levels[-1]:
        return ([built] if built else []), levels
    props = feat.get("properties") or {}
    try:
        line = single_line(shape(feat["geometry"]))
    except Exception:
        line = None
    if line is None or len(line.coords) < 2:
        return [built], levels
    climbs = climbs_along_way(props, list(line.coords), levels[0], levels[-1], vertex_levels)
    base_props = dict(built["properties"])
    if kind == "escalator" and props.get("conveying"):
        base_props["conveying"] = props["conveying"]
    pieces = sloped_features(kind, line, levels, base_props, climbs)
    return (pieces or [built]), levels


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="_tmp_indoor.json")
    p.add_argument("--output", default="indoor.json")
    p.add_argument("--levels-out", default="www/indoor-levels.json")
    args = p.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"✗  {src} introuvable", file=sys.stderr)
        sys.exit(1)

    features = json.loads(src.read_text()).get("features", [])
    out, level_counts, kinds = [], Counter(), Counter()
    skipped = 0
    vertex_levels = build_vertex_levels(features)
    for kind, feat in select_features(features):
        built, levels = build_features(kind, feat, vertex_levels)
        if not built:
            skipped += 1
            continue
        out.extend(built)
        kinds[kind] += 1
        for value in levels:
            level_counts[value] += 1

    Path(args.output).write_text(json.dumps(
        {"type": "FeatureCollection", "features": out}, ensure_ascii=False))

    levels_doc = {
        "levels": [{"level": format_level(v), "count": level_counts[v]}
                   for v in sorted(level_counts)],
    }
    Path(args.levels_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.levels_out).write_text(json.dumps(levels_doc, indent=2, ensure_ascii=False) + "\n")

    detail = ", ".join(f"{k} {v}" for k, v in kinds.most_common())
    print(f"  {len(out)} features intérieur/souterrain ({detail}), {skipped} ignorées")
    print(f"  {len(level_counts)} niveaux → {args.levels_out}")


if __name__ == "__main__":
    main()
