import argparse
import json
import sys
from collections import Counter

from osm_levels import format_level, parse_level_values, underground_level

ROOF_LOCATIONS = {"roof", "rooftop"}
LEVEL_PROPS = ("level_min", "level_max", "level_approx", "level_hint")


def level_props(props):
    values = parse_level_values(props.get("level"), props.get("repeat_on"))
    if values:
        return {"level_min": format_level(values[0]), "level_max": format_level(values[-1])}, "level"
    approx = underground_level(props)
    if approx is not None:
        value = format_level(approx)
        return {"level_min": value, "level_max": value, "level_approx": "yes"}, "underground"
    if props.get("location") in ROOF_LOCATIONS:
        return {"level_hint": "roof"}, "roof"
    return {}, "default"


def assign_collection(collection):
    stats = Counter()
    for feat in collection.get("features", []):
        props = feat.get("properties")
        if not isinstance(props, dict):
            continue
        for key in LEVEL_PROPS:
            props.pop(key, None)
        extra, source = level_props(props)
        props.update(extra)
        stats[source] += 1
    return stats


def assign_file(path):
    with open(path) as f:
        collection = json.load(f)
    stats = assign_collection(collection)
    with open(path, "w") as out:
        json.dump(collection, out, ensure_ascii=False)
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)
    for path in args.paths:
        s = assign_file(path)
        print(f"  {path} : {s['level']} level, {s['underground']} souterrains déduits, "
              f"{s['roof']} toits, {s['default']} au rez-de-chaussée par défaut")
    return 0


if __name__ == "__main__":
    sys.exit(main())
