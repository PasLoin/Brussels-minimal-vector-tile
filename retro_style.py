#!/usr/bin/env python3
"""
retro_style.py  —  style.json MapLibre → map.config.yaml
Capture : color, color_private, pattern, pattern_private, outline_color, opacity
"""
import argparse, json, sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("✗  pip install pyyaml", file=sys.stderr); sys.exit(1)

GROUPS = {
    "landuse":          ["landuse-"],
    "water":            ["water-","waterway-"],
    "green":            ["green-"],
    "trees":            ["trees-"],
    "buildings":        ["buildings-"],
    "leisure":          ["leisure-","pitch-"],
    "roads":            ["roads-","road-"],
    "pedestrian":       ["pedestrian-"],
    "cycleway":         ["cycleway"],
    "railway":          ["railway-"],
    "public_transport": ["public_transport-"],
    "boundaries":       ["boundaries"],
    "poi":              ["poi-"],
}

LABELS = {
    "landuse":"Occupation du sol","water":"Eau","green":"Espaces verts",
    "trees":"Arbres et haies","buildings":"Bâtiments","leisure":"Loisirs",
    "roads":"Routes","pedestrian":"Piétons","cycleway":"Cyclable",
    "railway":"Ferroviaire","public_transport":"Transport STIB",
    "boundaries":"Limites administratives","poi":"POI",
}

GROUP_TAGS = {
    "landuse":  ["landuse"],
    "water":    ["waterway","natural"],
    "green":    ["leisure","natural","landuse"],
    "trees":    ["natural","barrier"],
    "buildings":["building"],
    "leisure":  ["leisure"],
    "roads":    ["highway"],
    "pedestrian":["highway"],
    "railway":  ["railway"],
    "poi":      ["amenity","shop","tourism"],
    "boundaries":["boundary"],
}

# ── Extraction d'une expression fill-color ────────────────────────────────────

def parse_color_expr(expr):
    """
    Retourne (color, color_private, pattern_private) depuis une expression MapLibre.
    Gère :
      "#hexcolor"
      ["case", ["==",["get","access"],"private"], "#priv", "#pub"]
      null  → (None, None, None)
    """
    if expr is None:
        return None, None, None
    if isinstance(expr, str) and expr.startswith("#"):
        return expr, None, None
    if isinstance(expr, list):
        if expr[0] == "case" and len(expr) == 4:
            cond, val_true, val_false = expr[1], expr[2], expr[3]
            # case access=private → col_private, sinon → col_public
            if (isinstance(cond, list) and cond[0] == "==" and
                    cond[1] == ["get","access"] and cond[2] == "private"):
                pub  = val_false if isinstance(val_false, str) else None
                priv = val_true  if isinstance(val_true,  str) else None
                return pub, priv, None
        # match/interpolate → dernière valeur
        if expr[0] in ("match","interpolate") and len(expr) >= 2:
            last = expr[-1]
            if isinstance(last, str) and last.startswith("#"):
                return last, None, None
    return None, None, None


def parse_opacity(paint):
    for k in ("fill-opacity","line-opacity","circle-opacity"):
        v = paint.get(k)
        if v is not None and isinstance(v, (int, float)):
            return round(float(v), 2)
    return None


def parse_outline_color(paint):
    """Extrait outline_color depuis un match sur fill-color ou line-color."""
    v = paint.get("line-color") or paint.get("fill-color")
    if isinstance(v, list) and v[0] == "match" and len(v) >= 4:
        # match ["get","leisure"] val1 col1 val2 col2 ... default
        # on prend le premier couple (val, col) qui a une couleur distincte
        colors = {}
        i = 2
        while i + 1 < len(v):
            val, col = v[i], v[i+1]
            if isinstance(val, str) and isinstance(col, str) and col.startswith("#"):
                colors[val] = col
            i += 2
        return colors
    return {}


def min_zoom_of(layer):
    z = layer.get("minzoom", 10)
    for block in (layer.get("paint",{}), layer.get("layout",{})):
        for val in block.values():
            if isinstance(val,list) and len(val)>3 and val[0]=="interpolate":
                try: z = max(z, int(val[3]))
                except: pass
    return max(int(z), 10)


def filter_values(filt, tag):
    if not isinstance(filt,list) or not filt: return []
    op = filt[0]
    if op == "==" and len(filt) == 3:
        lhs, rhs = filt[1], filt[2]
        if lhs == ["get",tag] or lhs == tag:
            return [str(rhs)] if isinstance(rhs,(str,int)) else []
    if op in ("in","match") and len(filt) >= 3:
        lhs = filt[1]
        if lhs == ["get",tag] or lhs == tag:
            vals = filt[2]
            if isinstance(vals,list) and vals[0]=="literal":
                return [str(v) for v in vals[1]]
            return [str(v) for v in filt[2:] if isinstance(v,str)]
    if op in ("any","all"):
        out = []
        for sub in filt[1:]: out += filter_values(sub, tag)
        return out
    return []


# ── Analyse principale ────────────────────────────────────────────────────────

def analyse_group(name, style_layers):
    prefixes = GROUPS[name]
    matched  = [l for l in style_layers
                if any(l["id"].startswith(p) for p in prefixes) and l.get("source")]
    if not matched: return None

    zmins  = [min_zoom_of(l) for l in matched]
    appear = min(zmins) if zmins else 10

    # Couleur principale du groupe (premier fill)
    main_color = None
    for l in matched:
        col, _, _ = parse_color_expr(l.get("paint",{}).get("fill-color"))
        if col: main_color = col; break

    visible = not any(
        l.get("layout",{}).get("visibility") == "none"
        for l in matched if not l["id"].endswith("-3d")
    )

    tags_to_check = GROUP_TAGS.get(name, ["type"])
    subtypes = {}  # val → {tag, color, color_private, pattern, pattern_private, outline_color, appear_at, opacity}

    # Outline colors depuis leisure-outline (match expression)
    outline_map = {}
    for l in matched:
        if "outline" in l["id"] or l.get("type") == "line":
            om = parse_outline_color(l.get("paint",{}))
            outline_map.update(om)

    for l in matched:
        paint = l.get("paint",{})
        filt  = l.get("filter")
        lz    = min_zoom_of(l)

        # fill-pattern → pattern ou pattern_private
        pattern     = paint.get("fill-pattern")
        is_private_layer = False
        if filt and isinstance(filt, list):
            # détecter si ce layer est conditionné par access=private
            def has_private_cond(f):
                if not isinstance(f, list): return False
                if f[0]=="==" and f[1]==["get","access"] and f[2]=="private": return True
                return any(has_private_cond(sub) for sub in f[1:] if isinstance(sub,list))
            is_private_layer = has_private_cond(filt)

        for tag in tags_to_check:
            if not filt: continue
            vals = filter_values(filt, tag)
            for v in vals:
                col, col_priv, _ = parse_color_expr(paint.get("fill-color"))
                op = parse_opacity(paint)
                if v not in subtypes:
                    subtypes[v] = {"tag": tag}

                if col and col != main_color:
                    subtypes[v]["color"] = col
                if col_priv:
                    subtypes[v]["color_private"] = col_priv
                if pattern and is_private_layer:
                    subtypes[v]["pattern_private"] = str(pattern)
                elif pattern and not is_private_layer:
                    subtypes[v]["pattern"] = str(pattern)
                if op is not None and abs(op - 1.0) > 0.01:
                    subtypes[v]["opacity"] = op
                if lz > appear:
                    subtypes[v]["appear_at"] = lz
                if v in outline_map:
                    subtypes[v]["outline_color"] = outline_map[v]

    # Nettoyage
    cleaned = {}
    for k, v in subtypes.items():
        entry = {"tag": v["tag"]}
        for prop in ("color","color_private","pattern","pattern_private",
                     "outline_color","appear_at","opacity"):
            if prop in v: entry[prop] = v[prop]
        cleaned[k] = entry

    return {"appear_at":appear,"main_color":main_color,
            "visible":visible,"subtypes":cleaned}


# ── Sérialisation YAML ────────────────────────────────────────────────────────

def format_subtype(scfg):
    """Sérialise un dict sous-type en ligne inline YAML."""
    FIELD_ORDER = ["tag","color","color_private","pattern","pattern_private",
                   "outline_color","appear_at","opacity"]
    parts = []
    for f in FIELD_ORDER:
        if f not in scfg: continue
        v = scfg[f]
        if isinstance(v, str) and v.startswith("#"):
            parts.append(f'{f}: "{v}"')
        elif isinstance(v, str):
            parts.append(f'{f}: {v}')
        elif isinstance(v, float):
            parts.append(f'{f}: {v}')
        else:
            parts.append(f'{f}: {v}')
    return "{ " + ", ".join(parts) + " }"


def dump_layer(name, info):
    lines = []
    label  = LABELS.get(name, name.capitalize())
    appear = info["appear_at"]
    col    = info["main_color"]

    lines.append(f"  {name}:")
    lines.append(f"    label: {label}")
    if col: lines.append(f'    color: "{col}"')
    if not info["visible"]: lines.append(f"    visible: false")
    lines.append(f"    appear_at: {appear}")
    if info["subtypes"]:
        lines.append(f"    subtypes:")
        for val, scfg in sorted(info["subtypes"].items()):
            lines.append(f"      {val}: {format_subtype(scfg)}")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="style.json → map.config.yaml")
    p.add_argument("--style", default="www/style.json")
    p.add_argument("--out",   default="map.config.yaml")
    args = p.parse_args()

    style_path = Path(args.style)
    if not style_path.exists():
        print(f"✗  {style_path} introuvable", file=sys.stderr); sys.exit(1)

    with open(style_path) as f:
        style = json.load(f)
    style_layers = style.get("layers",[])
    print(f"→ {len(style_layers)} layers lus depuis {style_path}")

    bg     = next((l["paint"].get("background-color","#f2efe9")
                   for l in style_layers if l.get("type")=="background"), "#f2efe9")
    glyphs = style.get("glyphs",
        "https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf")

    groups = {}
    for name in GROUPS:
        info = analyse_group(name, style_layers)
        if not info: continue
        groups[name] = info
        st_n = len(info["subtypes"])
        specials = sum(1 for s in info["subtypes"].values()
                       if any(k in s for k in ("color_private","pattern","pattern_private","outline_color")))
        print(f"   {name:22s} appear_at={info['appear_at']:2d}  "
              f"color={info['main_color'] or '—':9s}  "
              f"{st_n} sous-types  {specials} spéciaux")

    out_lines = [
        "# ─────────────────────────────────────────────────────────────────────",
        f"# map.config.yaml  —  généré depuis {style_path}  par retro_style.py",
        "#",
        "# Champs disponibles par sous-type :",
        "#   tag            tag OSM du filtre (landuse, leisure, natural, highway...)",
        "#   color          couleur principale",
        "#   color_private  couleur si access=private",
        "#   pattern        fill-pattern (ex: military-hatch)",
        "#   pattern_private  fill-pattern uniquement si access=private (ex: green-hatch)",
        "#   outline_color  couleur du contour",
        "#   opacity        opacité fill (0.0–1.0)",
        "#   appear_at      zoom minimum",
        "#",
        "# Modifier CE fichier, pas style.json directement.",
        "# Regénérer :  python3 build_map.py",
        "# ─────────────────────────────────────────────────────────────────────",
        "",
        "map:",
        "  name: Map",
        "  center: [4.3517, 50.8503]",
        "  zoom: 13",
        f'  background: "{bg}"',
        '  font: "#734a08"',
        f'  glyphs: "{glyphs}"',
        "","",
        "layers:","",
    ]

    for name, info in groups.items():
        out_lines.append(dump_layer(name, info))
        out_lines.append("")

    Path(args.out).write_text("\n".join(out_lines))
    print(f"\n✓  {args.out}  ({len(groups)} couches)")
    print(f"\n→  Éditer {args.out}, puis :  python3 build_map.py --config {args.out}")

if __name__ == "__main__":
    main()
