#!/usr/bin/env python3
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

POINT = {"Point", "MultiPoint"}
LINE = {"LineString", "MultiLineString"}
AREA = {"Polygon", "MultiPolygon"}

KINDS = {
    "point": POINT,
    "line": LINE,
    "area": AREA,
    "line_or_area": LINE | AREA,
    "area_or_line": LINE | AREA,
    "area_or_point": AREA | POINT,
    "to_point": POINT | LINE | AREA,
    "any": POINT | LINE | AREA,
}

POLICIES = {
    "roads":            [("highway", "line"), ("man_made", "area_or_line")],
    "water":            [("waterway", "line"), ("*", "area")],
    "green":            [("*", "area")],
    "trees":            [("natural=tree", "point"), ("*", "line_or_area")],
    "landuse":          [("*", "area")],
    "boundaries":       [("*", "line_or_area")],
    "leisure":          [("*", "area_or_point")],
    "pedestrian":       [("area=yes", "area_or_line"), ("*", "line_or_area")],
    "cycleway":         [("*", "line")],
    "railway":          [("*", "line")],
    "street_furniture": [("barrier=fence", "line_or_area"), ("*", "to_point")],
    "poi":              [("*", "area_or_point")],
}

OSM_TYPES = {"n": "node", "w": "way", "r": "relation"}


def parse_filter(expr):
    types = {"node", "way", "relation"}
    if "/" in expr:
        prefix, expr = expr.split("/", 1)
        types = {OSM_TYPES[ch] for ch in prefix if ch in OSM_TYPES}
    if "=" in expr:
        key, raw = expr.split("=", 1)
        values = None if raw == "*" else set(raw.split(","))
    else:
        key, values = expr, None
    return types, key, values


def matches_filters(props, filters):
    osm_type = props.get("@type")
    for types, key, values in filters:
        if osm_type is not None and osm_type not in types:
            continue
        if key not in props:
            continue
        if values is None or str(props[key]) in values:
            return True
    return False


def selector_matches(selector, props):
    if selector == "*":
        return True
    if "=" in selector:
        key, value = selector.split("=", 1)
        return str(props.get(key)) == value
    return selector in props


def kind_for(props, policy):
    for selector, kind in policy:
        if selector_matches(selector, props):
            return kind
    return "any"


def representative_point(geometry):
    from shapely.geometry import mapping, shape
    geom = shape(geometry)
    if geom.is_empty:
        return None
    if geom.geom_type in ("LineString", "MultiLineString"):
        if geom.geom_type == "MultiLineString":
            geom = max(geom.geoms, key=lambda g: g.length)
        pt = geom.interpolate(0.5, normalized=True)
    else:
        if not geom.is_valid:
            geom = geom.buffer(0)
        pt = geom.representative_point()
    return mapping(pt)


def osm_key(props):
    return (props.get("@type"), props.get("@id"))


def filter_features(features, filters, policy):
    stats = Counter()
    candidates = []
    has_area = set()
    has_line = set()
    for feat in features:
        props = feat.get("properties") or {}
        gtype = (feat.get("geometry") or {}).get("type")
        if not matches_filters(props, filters):
            stats["tags"] += 1
            continue
        kind = kind_for(props, policy)
        if gtype not in KINDS[kind]:
            stats["geometry"] += 1
            continue
        if gtype in AREA:
            has_area.add(osm_key(props))
        if gtype in LINE:
            has_line.add(osm_key(props))
        candidates.append((feat, kind, gtype))
    kept = []
    converted = set()
    for feat, kind, gtype in candidates:
        props = feat.get("properties") or {}
        key = osm_key(props)
        if kind == "area_or_line" and gtype in LINE and key in has_area:
            stats["duplicate"] += 1
            continue
        if kind == "line_or_area" and gtype in AREA and key in has_line:
            stats["duplicate"] += 1
            continue
        if kind == "to_point" and gtype not in POINT:
            if key in converted:
                stats["duplicate"] += 1
                continue
            point = representative_point(feat["geometry"])
            if point is None:
                stats["geometry"] += 1
                continue
            converted.add(key)
            feat["geometry"] = point
            stats["converted"] += 1
        kept.append(feat)
    return kept, stats


def strip_attributes(features):
    for feat in features:
        props = feat.get("properties") or {}
        for key in ("@id", "@type"):
            props.pop(key, None)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("path")
    p.add_argument("--layer", required=True)
    p.add_argument("--filters", nargs="+", required=True)
    p.add_argument("--keep-attributes", action="store_true")
    args = p.parse_args()

    path = Path(args.path)
    data = json.loads(path.read_text())
    features = data.get("features", [])
    filters = [parse_filter(f) for f in args.filters]
    policy = POLICIES.get(args.layer, [("*", "any")])

    kept, stats = filter_features(features, filters, policy)
    if not args.keep_attributes:
        strip_attributes(kept)
    data["features"] = kept
    path.write_text(json.dumps(data, ensure_ascii=False))
    print(f"  filtre {args.layer} : {len(features)} → {len(kept)} "
          f"(tags hors filtre {stats['tags']}, géométrie {stats['geometry']}, "
          f"doublons ligne/surface {stats['duplicate']}, convertis en point {stats['converted']})")


if __name__ == "__main__":
    sys.exit(main())
