import math
import re

LEVEL_TOKEN = re.compile(r"^\s*(-?\d+(?:\.\d+)?)(?:\s*-\s*(-?\d+(?:\.\d+)?))?\s*$")

UNDERGROUND_HINTS = (
    ("tunnel", {"yes"}),
    ("indoor", {"yes"}),
    ("location", {"underground"}),
)


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
        layer = None
    if layer is not None and layer < 0:
        for key, accepted in UNDERGROUND_HINTS:
            if props.get(key) in accepted:
                return float(math.trunc(layer))
        return None
    if props.get("location") == "underground":
        return -1.0
    return None


def format_level(value):
    return int(value) if float(value).is_integer() else value
