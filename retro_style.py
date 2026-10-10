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

from build_map import _lighten

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
    "street_furniture": ["street-furniture-"],
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
    "street_furniture": "Mobilier urbain",
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
    "street_furniture": ["amenity", "barrier", "highway", "entrance"],
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
        if isinstance(val_false, str) and val_false.startswith("#"):
            return val_false, None

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
    if "minzoom" in layer:
        return max(int(layer["minzoom"]), 10)
    return 10


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
    if op == "has" and len(filt) == 2 and filt[1] == tag:
        return [str(tag)]
    if op in ("any", "all"):
        out = []
        for sub in filt[1:]:
            out += filter_values(sub, tag)
        return out
    return []


LABEL_KEYS = ("name", "ref")


def is_label_key(key):
    return isinstance(key, str) and (key in LABEL_KEYS or key.startswith(("name:", "addr:")))


def refers_to_label(expr):
    if isinstance(expr, list):
        if len(expr) == 2 and expr[0] == "get" and is_label_key(expr[1]):
            return True
        return any(refers_to_label(e) for e in expr)
    return False


def is_label_layer(layer):
    if layer.get("type") != "symbol":
        return False
    return refers_to_label(layer.get("layout", {}).get("text-field"))


def parse_by(expr, group_tags):
    if (isinstance(expr, list) and len(expr) >= 5 and expr[0] == "match"
            and isinstance(expr[1], list) and len(expr[1]) == 2 and expr[1][0] == "get"
            and expr[1][1] not in group_tags and not is_label_key(expr[1][1])):
        mapping = {}
        for label, out in zip(expr[2:-1:2], expr[3:-1:2]):
            if isinstance(label, str) and isinstance(out, str):
                mapping[label] = out
        if mapping and isinstance(expr[-1], str):
            return expr[1][1], mapping, expr[-1]
    return None


def is_variant_layer(layer):
    lid = layer["id"]
    return "tunnel" in lid or "bridge" in lid


def is_casing_layer(layer):
    return "-casing" in layer["id"]


def is_outline_layer(layer):
    return layer["id"].endswith("-outline")


def step_threshold(expr):
    if (isinstance(expr, list) and len(expr) >= 5 and expr[0] == "step"
            and expr[1] == ["zoom"] and isinstance(expr[3], (int, float))):
        return int(expr[3])
    return None


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
    for l in layers:
        if not any(l["id"].startswith(p) for p in prefixes):
            continue
        if is_label_layer(l):
            z = int(l.get("minzoom", 10))
            st = step_threshold(l["layout"]["text-field"])
            if st is not None:
                z = max(z, st)
            return max(z, 10)
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
    primary = [l for l in matched
               if not (is_casing_layer(l) or is_variant_layer(l) or is_label_layer(l))]
    for l in primary + matched:
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

        if is_label_layer(l):
            continue

        pattern = paint.get("fill-pattern")
        is_private_layer = has_private_condition(filt) if filt else False
        variant = is_variant_layer(l)
        casing = is_casing_layer(l)
        outline = is_outline_layer(l)

        for tag in tags_to_check:
            if not filt:
                continue
            vals = filter_values(filt, tag)
            for v in vals:
                color_expr = (paint.get("fill-color") or paint.get("line-color") or
                              paint.get("circle-color") or paint.get("text-color"))
                col, col_priv = parse_color_expr(color_expr)
                by_col = parse_by(color_expr, tags_to_check)
                if by_col:
                    col = by_col[2]
                op = parse_opacity(paint)

                if v not in subtypes:
                    subtypes[v] = {"tag": tag}

                subtypes[v]["appear_at"] = min(subtypes[v].get("appear_at", lz), lz)

                if variant:
                    if "tunnel" in l["id"] and not casing and col:
                        subtypes[v]["tunnel_color"] = col
                    continue
                if casing or outline:
                    if col:
                        subtypes[v]["outline_color"] = col
                    continue

                if col:
                    subtypes[v]["color"] = col
                if col_priv:
                    subtypes[v]["color_private"] = col_priv
                if by_col:
                    subtypes[v]["by"] = by_col[0]
                    subtypes[v]["by_color"] = by_col[1]
                by_pat = parse_by(pattern, tags_to_check)
                if by_pat:
                    subtypes[v]["by"] = by_pat[0]
                    subtypes[v]["by_pattern"] = by_pat[1]
                    pattern = by_pat[2]
                if pattern and is_private_layer:
                    subtypes[v]["pattern_private"] = str(pattern)
                elif pattern and not is_private_layer:
                    subtypes[v]["pattern"] = str(pattern)
                    subtypes[v]["pattern_at"] = lz
                if op is not None and abs(op - 1.0) > 0.01:
                    subtypes[v]["opacity"] = op
                if v in outline_map and "outline_color" not in subtypes[v]:
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
                        subtypes[val]["appear_at"] = min(subtypes[val].get("appear_at", lz), lz)
                        if not col:
                            continue
                        if outline:
                            subtypes[val]["outline_color"] = col
                        else:
                            subtypes[val]["color"] = col

    # Nettoyage : supprimer les champs redondants
    cleaned = {}
    for k, v in subtypes.items():
        entry = {"tag": v["tag"]}
        if "tunnel_color" in v and "color" in v and v["tunnel_color"] == _lighten(v["color"]):
            del v["tunnel_color"]
        if "pattern_at" in v and v["pattern_at"] == v.get("appear_at"):
            del v["pattern_at"]
        for prop in FIELD_ORDER[1:]:
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
    "tag", "color", "color_private", "tunnel_color", "pattern", "pattern_private",
    "pattern_at", "outline_color", "appear_at", "labels_at", "opacity",
    "by", "by_color", "by_pattern"
]


def flow_value(v):
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{flow_key(k)}: {flow_value(x)}" for k, x in sorted(v.items())) + " }"
    if isinstance(v, str):
        if v.startswith("#") or not re.fullmatch(r"[A-Za-z0-9_./-]+", v):
            return json.dumps(v, ensure_ascii=False)
        return v
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def flow_key(k):
    k = str(k)
    return k if re.fullmatch(r"[A-Za-z0-9_-]+", k) else json.dumps(k, ensure_ascii=False)


def format_subtype_inline(scfg):
    parts = [f"{f}: {flow_value(scfg[f])}" for f in FIELD_ORDER if f in scfg]
    return "{ " + ", ".join(parts) + " }"


def parse_sports(style_layers):
    by_id = {l["id"]: l for l in style_layers}
    fill = by_id.get("pitch-sport-fill")
    if not fill:
        return None
    values = defaultdict(dict)
    default = {}

    def collect(expr, field):
        if isinstance(expr, list) and expr and expr[0] == "match":
            for label, out in zip(expr[2:-1:2], expr[3:-1:2]):
                values[label][field] = out
            default[field] = expr[-1]
        elif expr is not None:
            default[field] = expr

    collect(fill.get("paint", {}).get("fill-color"), "color")
    outline = by_id.get("pitch-sport-outline")
    if outline:
        collect(outline.get("paint", {}).get("line-color"), "outline_color")
    sports = {}
    markings = by_id.get("pitch-markings")
    if markings:
        sports["markings_at"] = int(markings.get("minzoom", 17))
        size = markings.get("layout", {}).get("icon-size")
        try:
            length = size[4][1][3]
            collect(length, "length")
        except (TypeError, IndexError):
            pass
    sports["default"] = default
    sports["values"] = {k: dict(v) for k, v in sorted(values.items())}
    return sports


def dump_sports(sports):
    lines = ["    sports:"]
    if "markings_at" in sports:
        lines.append(f"      markings_at: {sports['markings_at']}")
    order = ("color", "outline_color", "length")
    def entry(d):
        return "{ " + ", ".join(f"{k}: {flow_value(d[k])}" for k in order if k in d) + " }"
    lines.append(f"      default: {entry(sports['default'])}")
    if sports["values"]:
        lines.append("      values:")
        for k, v in sports["values"].items():
            lines.append(f"        {k}: {entry(v)}")
    return lines


NO_LAYER_COLOR = {"roads"}


def dump_layer(name, info):
    lines = []
    label  = LABELS.get(name, name.capitalize())
    appear = info["appear_at"]
    col    = info["main_color"]
    bc     = info["border_color"]
    la     = info["labels_at"]

    lines.append(f"  {name}:")
    lines.append(f"    label: {label}")
    if col and name not in NO_LAYER_COLOR:
        lines.append(f'    color: "{col}"')
    if bc and name not in NO_LAYER_COLOR:
        lines.append(f'    border_color: "{bc}"')
    if not info["visible"]:
        lines.append(f"    visible: false")
    if info["extrusion_3d"]:
        lines.append(f"    extrusion_3d: true")
    lines.append(f"    appear_at: {appear}")
    if la and la != appear + 3:
        lines.append(f"    labels_at: {la}")
    if info.get("tiles"):
        lines.append(f"    tiles: {flow_value(info['tiles'])}")
    if info["subtypes"]:
        lines.append(f"    subtypes:")
        for val, scfg in sorted(info["subtypes"].items()):
            lines.append(f"      {val}: {format_subtype_inline(scfg)}")
    if info.get("sports"):
        lines += dump_sports(info["sports"])
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
        (l.get("paint", {}).get("background-color", "#f2efe9")
         for l in style_layers if l.get("type") == "background"),
        "#f2efe9"
    )
    if not isinstance(bg, str):
        bg = first_hex(bg) or "#f2efe9"
    glyphs = style.get("glyphs",
        "https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf")
    map_meta = (style.get("metadata") or {}).get("brussels:map") or {}
    map_name = style.get("name") or map_meta.get("name") or "Map"
    map_version = map_meta.get("version")
    map_center = style.get("center") or map_meta.get("center") or [4.3517, 50.8503]
    map_zoom = style.get("zoom", map_meta.get("zoom", 13))
    map_font = map_meta.get("font", "#734a08")

    metadata = style.get("metadata") or {}
    meta_tiles = metadata.get("brussels:tiles") or {}
    meta_patterns = metadata.get("brussels:patterns") or {}
    groups = {}
    for name in GROUPS:
        info = analyse_group(name, style_layers)
        if not info:
            continue
        if name in meta_tiles:
            info["tiles"] = meta_tiles[name]
        if name == "leisure":
            info["sports"] = parse_sports(style_layers)
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
        "#   tiles          paramètres PMTiles (min_zoom, max_zoom, simplification,",
        "#                  detail_from pour buildings)",
        "#   sports         leisure uniquement : rendu des terrains par sport_render",
        "#                  (markings_at, default, values: couleur, contour, longueur)",
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
        "#   pattern_at     zoom d'apparition du motif (défaut: appear_at)",
        "#   by             clé OSM secondaire (ex: religion, leaf_type)",
        "#   by_color       couleur par valeur de la clé \"by\" (défaut: color)",
        "#   by_pattern     motif par valeur de la clé \"by\" (défaut: pattern)",
        "#   tunnel_color   couleur des tronçons en tunnel (défaut: color éclaircie)",
        "#",
        "# Section patterns : motifs SVG chargés par la carte",
        "#   file, size (px), replace (substitution de couleurs dans le SVG)",
        "#",
        "# Modifier CE fichier, pas style.json directement.",
        "# Regénérer :  python3 build_map.py",
        "# ─────────────────────────────────────────────────────────────────────",
        "",
        "map:",
        f"  name: {json.dumps(map_name, ensure_ascii=False)}",
    ]
    if map_version is not None:
        out_lines.append(f"  version: {json.dumps(str(map_version))}")
    out_lines += [
        f"  center: [{map_center[0]}, {map_center[1]}]",
        f"  zoom: {map_zoom}",
        f'  background: "{bg}"',
        f'  font: "{map_font}"',
        f'  glyphs: "{glyphs}"',
        "",
    ]
    if meta_patterns:
        out_lines.append("patterns:")
        for pname, pcfg in sorted(meta_patterns.items()):
            out_lines.append(f"  {flow_key(pname)}: {flow_value(pcfg)}")
        out_lines.append("")
    out_lines += ["layers:", ""]

    for name, info in groups.items():
        out_lines.append(dump_layer(name, info))
        out_lines.append("")

    Path(args.out).write_text("\n".join(out_lines))
    print(f"\n✓  {args.out}  ({len(groups)} couches)")
    print(f"\n→  Éditer {args.out}, puis :  python3 build_map.py --config {args.out}")


if __name__ == "__main__":
    main()
