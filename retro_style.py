#!/usr/bin/env python3
"""
retro_style.py  —  style.json MapLibre → map.config.yaml
=========================================================
Capture COMPLÈTE de tous les champs supportés par build_map.py :
  color, color_private, pattern, pattern_private, outline_color,
  opacity, appear_at, labels_at, extrusion_3d, border_color,
  visible, subtypes (avec tag, color, appear_at, opacity, outline_color,
  pattern, pattern_private, color_private)

Garantie bidirectionnelle :
  style.json → retro_style.py → map.config.yaml
            → build_map.py   → style.json  (sémantiquement équivalent)
"""
import argparse, json, re, sys
from collections import defaultdict
from pathlib import Path

try:
    import yaml
except ImportError:
    print("✗  pip install pyyaml", file=sys.stderr); sys.exit(1)

# ── Groupes : préfixes de layer-id → nom de couche ────────────────────────────

GROUPS = {
    "landuse":          ["landuse-"],
    "water":            ["water-", "waterway-"],
    "green":            ["green-"],
    "trees":            ["trees-"],
    "buildings":        ["buildings-"],
    "leisure":          ["leisure-", "pitch-sport-"],
    "roads":            ["roads-", "road-", "man_made-"],
    "pedestrian":       ["pedestrian-"],
    "cycleway":         ["cycleway"],
    "railway":          ["railway-"],
    "public_transport": ["public_transport-"],
    "boundaries":       ["boundaries"],
    "poi":              ["poi-", "leisure-icon"],
}

LABELS = {
    "landuse":          "Occupation du sol",
    "water":            "Eau",
    "green":            "Espaces verts",
    "trees":            "Arbres et haies",
    "buildings":        "Bâtiments",
    "leisure":          "Loisirs",
    "roads":            "Routes",
    "pedestrian":       "Piétons",
    "cycleway":         "Cyclable",
    "railway":          "Ferroviaire",
    "public_transport": "Transport STIB",
    "boundaries":       "Limites administratives",
    "poi":              "POI",
}

# Tag OSM principal par couche (pour identifier les sous-types)
GROUP_TAGS = {
    "landuse":          ["landuse"],
    "water":            ["waterway", "natural"],
    "green":            ["leisure", "natural", "landuse"],
    "trees":            ["natural", "barrier"],
    "buildings":        ["building"],
    "leisure":          ["leisure"],
    "roads":            ["highway"],
    "pedestrian":       ["highway"],
    "railway":          ["railway"],
    "poi":              ["amenity", "shop", "tourism"],
    "boundaries":       ["boundary"],
    "cycleway":         ["highway"],
    "public_transport": ["route"],
}

# ── Helpers d'extraction d'expressions MapLibre ───────────────────────────────

def first_hex(expr):
    """Retourne la première couleur #hex trouvée dans une expression."""
    if isinstance(expr, str) and expr.startswith("#"):
        return expr
    if isinstance(expr, list):
        for item in expr:
            found = first_hex(item)
            if found:
                return found
    return None


def parse_color_expr(expr):
    """
    Extrait (color, color_private) depuis une expression fill-color / line-color.
    Gère :
      "#hexcolor"
      ["case", ["==",["get","access"],"private"], "#priv", "#pub"]
      ["match", ["get","X"], val1, col1, ..., default]
      None → (None, None)
    """
    if expr is None:
        return None, None
    if isinstance(expr, str):
        return (expr if expr.startswith("#") else None), None
    if not isinstance(expr, list) or not expr:
        return None, None

    op = expr[0]

    if op == "case" and len(expr) == 4:
        cond, val_true, val_false = expr[1], expr[2], expr[3]
        if (isinstance(cond, list) and len(cond) == 3
                and cond[0] == "==" and cond[1] == ["get", "access"]
                and cond[2] == "private"):
            pub  = val_false if isinstance(val_false, str) and val_false.startswith("#") else None
            priv = val_true  if isinstance(val_true,  str) and val_true.startswith("#")  else None
            return pub, priv

    if op in ("match", "interpolate"):
        last = expr[-1]
        if isinstance(last, str) and last.startswith("#"):
            return last, None

    if op == "coalesce":
        for item in expr[1:]:
            col, priv = parse_color_expr(item)
            if col:
                return col, priv

    return None, None


def parse_match_subtypes(expr, tag):
    """
    Extrait { value: color } depuis ["match", ["get", tag], v1, c1, v2, c2, ..., default].
    Retourne un dict vide si le format ne correspond pas.
    """
    out = {}
    if not isinstance(expr, list) or len(expr) < 4:
        return out
    if expr[0] != "match":
        return out
    key_expr = expr[1]
    if key_expr != ["get", tag]:
        return out
    # paires (valeur, couleur) suivies d'une valeur par défaut
    i = 2
    while i + 1 < len(expr):
        val, col = expr[i], expr[i + 1]
        if isinstance(val, str) and isinstance(col, str) and col.startswith("#"):
            out[val] = col
        i += 2
    return out


def parse_opacity(paint):
    for k in ("fill-opacity", "line-opacity", "circle-opacity"):
        v = paint.get(k)
        if isinstance(v, (int, float)):
            return round(float(v), 2)
    return None


def min_zoom_of(layer):
    z = layer.get("minzoom", 10)
    for block in (layer.get("paint", {}), layer.get("layout", {})):
        for val in block.values():
            if (isinstance(val, list) and len(val) > 3
                    and val[0] in ("interpolate", "step")):
                try:
                    z = min(z, int(val[3]))
                except (TypeError, ValueError):
                    pass
    return max(int(z), 10)


def max_zoom_of(layer):
    z = layer.get("maxzoom", 18)
    return int(z)


def filter_values(filt, tag):
    """Extrait les valeurs de tag depuis un filtre MapLibre."""
    if not isinstance(filt, list) or not filt:
        return []
    op = filt[0]
    if op == "==" and len(filt) == 3:
        lhs, rhs = filt[1], filt[2]
        if lhs == ["get", tag] or lhs == tag:
            return [str(rhs)] if isinstance(rhs, (str, int)) else []
    if op in ("in", "match") and len(filt) >= 3:
        lhs = filt[1]
        if lhs == ["get", tag] or lhs == tag:
            vals = filt[2]
            if isinstance(vals, list) and vals and vals[0] == "literal":
                return [str(v) for v in vals[1]]
            return [str(v) for v in filt[2:] if isinstance(v, str)]
    if op in ("any", "all"):
        out = []
        for sub in filt[1:]:
            out += filter_values(sub, tag)
        return out
    return []


def has_private_condition(filt):
    """Détecte si un filtre conditionne access=private."""
    if not isinstance(filt, list):
        return False
    if (filt[0] == "==" and len(filt) == 3
            and filt[1] == ["get", "access"] and filt[2] == "private"):
        return True
    return any(has_private_condition(sub) for sub in filt[1:] if isinstance(sub, list))


# ── Extraction des symboles (labels_at) ───────────────────────────────────────

def extract_labels_at(layers, prefixes):
    """Trouve le minzoom du premier layer symbol du groupe."""
    for l in layers:
        if not any(l["id"].startswith(p) for p in prefixes):
            continue
        if l.get("type") == "symbol" and "text-field" in l.get("layout", {}):
            return max(int(l.get("minzoom", 10)), 10)
    return None


# ── Extraction des border_color (buildings) ───────────────────────────────────

def extract_border_color(layers, prefixes):
    for l in layers:
        if not any(l["id"].startswith(p) for p in prefixes):
            continue
        if l.get("type") == "line" and "outline" in l["id"]:
            col = l.get("paint", {}).get("line-color")
            if isinstance(col, str) and col.startswith("#"):
                return col
    return None


# ── Analyse principale d'un groupe ───────────────────────────────────────────

def analyse_group(name, style_layers):
    prefixes = GROUPS[name]
    matched = [l for l in style_layers
               if any(l["id"].startswith(p) for p in prefixes)
               and l.get("source")]
    if not matched:
        return None

    # ── Visibilité ──
    visible = not any(
        l.get("layout", {}).get("visibility") == "none"
        for l in matched
        if not l["id"].endswith("-3d")
    )

    # ── Zoom d'apparition ──
    zmins = [min_zoom_of(l) for l in matched]
    appear = min(zmins) if zmins else 10

    # ── extrusion_3d ──
    extrusion_3d = any(l.get("type") == "fill-extrusion" for l in matched)

    # ── labels_at ──
    labels_at = extract_labels_at(matched, prefixes)

    # ── border_color ──
    border_color = extract_border_color(matched, prefixes)

    # ── Couleur principale du groupe ──
    # Priorité : premier fill, puis premier line
    main_color = None
    for l in matched:
        paint = l.get("paint", {})
        for key in ("fill-color", "line-color", "circle-color"):
            col, _ = parse_color_expr(paint.get(key))
            if col:
                main_color = col
                break
        if main_color:
            break

    # ── Sous-types ──
    tags_to_check = GROUP_TAGS.get(name, ["type"])
    subtypes = {}   # val → {tag, color, color_private, pattern, pattern_private,
                    #         outline_color, appear_at, opacity}

    # Précollecte des outline_color depuis layers de type "line" avec match
    outline_map = {}
    for l in matched:
        if l.get("type") != "line":
            continue
        paint = l.get("paint", {})
        for color_key in ("line-color",):
            expr = paint.get(color_key)
            for tag in tags_to_check:
                om = parse_match_subtypes(expr, tag)
                outline_map.update(om)

    # Parcours des layers pour extraire les sous-types
    for l in matched:
        paint  = l.get("paint", {})
        layout = l.get("layout", {})
        filt   = l.get("filter")
        ltype  = l.get("type")
        lz     = min_zoom_of(l)

        # Pattern
        pattern = paint.get("fill-pattern")
        is_private_layer = has_private_condition(filt) if filt else False

        for tag in tags_to_check:
            if not filt:
                continue
            vals = filter_values(filt, tag)
            for v in vals:
                col, col_priv = parse_color_expr(paint.get("fill-color") or
                                                  paint.get("line-color") or
                                                  paint.get("circle-color"))
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
                if v in outline_map and outline_map[v] != main_color:
                    subtypes[v]["outline_color"] = outline_map[v]

        # Match expressions sur fill-color pour les layers sans filtre explicite
        # (ex: leisure-fill utilise un ["match", ["get","leisure"], ...])
        filt_str = json.dumps(filt) if filt else ""
        if not filt or (isinstance(filt, list) and filt[0] in ("==", "all")
                        and "geometry-type" in filt_str):
            for tag in tags_to_check:
                for color_key in ("fill-color", "line-color"):
                    expr = paint.get(color_key)
                    subtypes_from_match = parse_match_subtypes(expr, tag)
                    for val, col in subtypes_from_match.items():
                        if val not in subtypes:
                            subtypes[val] = {"tag": tag}
                        if col and col != main_color:
                            subtypes[val]["color"] = col
                        if lz > appear:
                            subtypes[val].setdefault("appear_at", lz)

    # Nettoyage : supprimer les champs redondants
    cleaned = {}
    for k, v in subtypes.items():
        entry = {"tag": v["tag"]}
        for prop in ("color", "color_private", "pattern", "pattern_private",
                     "outline_color", "appear_at", "opacity"):
            if prop in v:
                entry[prop] = v[prop]
        cleaned[k] = entry

    return {
        "appear_at":    appear,
        "main_color":   main_color,
        "border_color": border_color,
        "visible":      visible,
        "extrusion_3d": extrusion_3d,
        "labels_at":    labels_at,
        "subtypes":     cleaned,
    }


# ── Sérialisation YAML ────────────────────────────────────────────────────────

FIELD_ORDER = [
    "tag", "color", "color_private", "pattern", "pattern_private",
    "outline_color", "appear_at", "labels_at", "opacity"
]


def format_subtype_inline(scfg):
    """Sérialise un dict sous-type en ligne inline YAML."""
    parts = []
    for f in FIELD_ORDER:
        if f not in scfg:
            continue
        v = scfg[f]
        if isinstance(v, str) and v.startswith("#"):
            parts.append(f'{f}: "{v}"')
        elif isinstance(v, str):
            parts.append(f'{f}: {v}')
        else:
            parts.append(f'{f}: {v}')
    return "{ " + ", ".join(parts) + " }"


def dump_layer(name, info):
    lines = []
    label  = LABELS.get(name, name.capitalize())
    appear = info["appear_at"]
    col    = info["main_color"]
    bc     = info["border_color"]
    la     = info["labels_at"]

    lines.append(f"  {name}:")
    lines.append(f"    label: {label}")
    if col:
        lines.append(f'    color: "{col}"')
    if bc:
        lines.append(f'    border_color: "{bc}"')
    if not info["visible"]:
        lines.append(f"    visible: false")
    if info["extrusion_3d"]:
        lines.append(f"    extrusion_3d: true")
    lines.append(f"    appear_at: {appear}")
    if la and la != appear + 3:
        lines.append(f"    labels_at: {la}")
    if info["subtypes"]:
        lines.append(f"    subtypes:")
        for val, scfg in sorted(info["subtypes"].items()):
            lines.append(f"      {val}: {format_subtype_inline(scfg)}")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="style.json → map.config.yaml")
    p.add_argument("--style", default="www/style.json")
    p.add_argument("--out",   default="map.config.yaml")
    args = p.parse_args()

    style_path = Path(args.style)
    if not style_path.exists():
        print(f"✗  {style_path} introuvable", file=sys.stderr)
        sys.exit(1)

    with open(style_path) as f:
        style = json.load(f)
    style_layers = style.get("layers", [])
    print(f"→ {len(style_layers)} layers lus depuis {style_path}")

    # Métadonnées globales
    bg = next(
        (l["paint"].get("background-color", "#f2efe9")
         for l in style_layers if l.get("type") == "background"),
        "#f2efe9"
    )
    glyphs = style.get("glyphs",
        "https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf")

    groups = {}
    for name in GROUPS:
        info = analyse_group(name, style_layers)
        if not info:
            continue
        groups[name] = info
        st_n = len(info["subtypes"])
        specials = sum(
            1 for s in info["subtypes"].values()
            if any(k in s for k in ("color_private", "pattern", "pattern_private", "outline_color"))
        )
        extr = " [3d]" if info["extrusion_3d"] else ""
        lab  = f" labels_at={info['labels_at']}" if info["labels_at"] else ""
        print(f"   {name:22s} appear_at={info['appear_at']:2d}"
              f"  color={info['main_color'] or '—':9s}"
              f"  {st_n} sous-types  {specials} spéciaux{extr}{lab}")

    out_lines = [
        "# ─────────────────────────────────────────────────────────────────────",
        f"# map.config.yaml  —  généré depuis {style_path}  par retro_style.py",
        "#",
        "# Champs disponibles par couche :",
        "#   label          nom lisible",
        "#   color          couleur principale (fill ou line)",
        "#   border_color   couleur du contour (buildings...)",
        "#   visible        false pour masquer la couche",
        "#   extrusion_3d   true pour activer le rendu 3D buildings",
        "#   appear_at      zoom minimum d'apparition",
        "#   labels_at      zoom minimum des étiquettes (défaut: appear_at+3)",
        "#   opacity        opacité globale (0.0–1.0)",
        "#",
        "# Champs disponibles par sous-type :",
        "#   tag            tag OSM du filtre (landuse, leisure, natural, highway...)",
        "#   color          couleur principale",
        "#   color_private  couleur si access=private",
        "#   pattern        fill-pattern (ex: military-hatch)",
        "#   pattern_private  fill-pattern uniquement si access=private (ex: green-hatch)",
        "#   outline_color  couleur du contour",
        "#   appear_at      zoom minimum",
        "#   opacity        opacité fill (0.0–1.0)",
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
        "", "",
        "layers:", "",
    ]

    for name, info in groups.items():
        out_lines.append(dump_layer(name, info))
        out_lines.append("")

    Path(args.out).write_text("\n".join(out_lines))
    print(f"\n✓  {args.out}  ({len(groups)} couches)")
    print(f"\n→  Éditer {args.out}, puis :  python3 build_map.py --config {args.out}")


if __name__ == "__main__":
    main()
