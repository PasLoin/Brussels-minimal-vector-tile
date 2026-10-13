#!/usr/bin/env python3
import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

try:
    import numpy as np
    import shapely
    from shapely.geometry import mapping, shape
except ImportError:
    print("✗  pip install shapely", file=sys.stderr)
    sys.exit(1)

LINE = {"LineString", "MultiLineString"}
AREA = {"Polygon", "MultiPolygon"}
POINT = {"Point", "MultiPoint"}

LINE_WIDTHS = {
    "wall": 0.15,
    "steps": 1.5,
    "corridor": 1.5,
    "footway": 1.2,
    "pedestrian": 3.0,
    "platform": 2.5,
    "elevator": 1.8,
}
POINT_SIZES = {"elevator": 1.8, "platform": 2.0}

PREFERS_AREA = {"room", "area", "corridor", "platform", "pedestrian", "elevator"}

UNDERGROUND_HINTS = (
    ("tunnel", {"yes"}),
    ("indoor", {"yes"}),
    ("location", {"underground"}),
)

LEVEL_TOKEN = re.compile(r"^\s*(-?\d+(?:\.\d+)?)(?:\s*-\s*(-?\d+(?:\.\d+)?))?\s*$")

KEEP_PROPS = ("name", "ref", "level", "repeat_on")


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


def parse_level_values(*raw_values):
    values = set()
    for raw in raw_values:
        if raw is None:
            continue
        for token in str(raw).split(";"):
            m = LEVEL_TOKEN.match(token)
            if not m:
                continue
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) is not None else a
            lo, hi = min(a, b), max(a, b)
            values.update((lo, hi))
            for z in range(math.ceil(lo), math.floor(hi) + 1):
                values.add(float(z))
    return sorted(values)


def underground_level(props):
    try:
        layer = float(str(props.get("layer", "")).strip())
    except ValueError:
        return None
    if layer >= 0:
        return None
    for key, accepted in UNDERGROUND_HINTS:
        if props.get(key) in accepted:
            return float(math.trunc(layer))
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


def format_level(value):
    return int(value) if float(value).is_integer() else value


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
    for kind, feat in select_features(features):
        built, levels = build_feature(kind, feat)
        if built is None:
            skipped += 1
            continue
        out.append(built)
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
