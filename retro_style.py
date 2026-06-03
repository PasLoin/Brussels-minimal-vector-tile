#!/usr/bin/env python3
"""
retro_style.py
──────────────
Lit un style.json MapLibre existant et produit un map.config.yaml
human-friendly (Option C).

Utilisations :
  # Bootstrap initial depuis le style Brussels existant
  python3 retro_style.py --style www/style.json --out map.config.yaml

  # Reverser n'importe quel style externe
  python3 retro_style.py --style other/style.json --out other.config.yaml

Le YAML produit est directement utilisable par build_map.py.
"""

import argparse, json, sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("✗  pip install pyyaml", file=sys.stderr); sys.exit(1)

# ── Groupes logiques : prefix de layer-id → nom de couche ────────────────────
GROUPS = {
    "landuse":          ["landuse-"],
    "water":            ["water-", "waterway-"],
    "green":            ["green-"],
    "trees":            ["trees-"],
    "buildings":        ["buildings-"],
    "leisure":          ["leisure-", "pitch-"],
    "roads":            ["roads-", "road-"],
    "pedestrian":       ["pedestrian-"],
    "cycleway":         ["cycleway"],
    "railway":          ["railway-"],
    "public_transport": ["public_transport-"],
    "boundaries":       ["boundaries"],
    "poi":              ["poi-"],
}

# Quel tag OSM identifie les sous-types de chaque couche
LAYER_TAG = {
    "landuse": "landuse", "green": "landuse", "water": "waterway",
    "trees": "natural",   "buildings": "building", "leisure": "leisure",
    "roads": "highway",   "pedestrian": "highway", "railway": "railway",
    "poi": "amenity",     "boundaries": "boundary",
}

# Noms lisibles par couche
LABELS = {
    "landuse": "Occupation du sol", "water": "Eau",
    "green": "Espaces verts",       "trees": "Arbres et haies",
    "buildings": "Bâtiments",       "leisure": "Loisirs",
    "roads": "Routes",              "pedestrian": "Piétons",
    "cycleway": "Cyclable",         "railway": "Ferroviaire",
    "public_transport": "Transport public",
    "boundaries": "Limites administratives", "poi": "POI",
}

# ── Helpers d'extraction ──────────────────────────────────────────────────────

def first_color(paint):
    """Retourne la première couleur hexadécimale trouvée dans un objet paint."""
    for key in ("fill-color", "line-color", "circle-color",
                "text-color", "icon-color", "fill-extrusion-color"):
        v = paint.get(key)
        if not v:
            continue
        if isinstance(v, str) and v.startswith("#"):
            return v
        if isinstance(v, list):
            # match/case → dernier élément = défaut
            if v[0] in ("match", "case") and len(v) >= 2:
                last = v[-1]
                if isinstance(last, str) and last.startswith("#"):
                    return last
            # interpolate → dernière valeur
            if v[0] == "interpolate" and len(v) > 4:
                last = v[-1]
                if isinstance(last, str) and last.startswith("#"):
                    return last
    return None


def min_zoom_of(layer):
    z = layer.get("minzoom", 0)
    # Affine via les stops d'interpolation
    for block in (layer.get("paint", {}), layer.get("layout", {})):
        for v in block.values():
            if isinstance(v, list) and len(v) > 3 and v[0] == "interpolate":
                try:
                    z = max(z, int(v[3]))
                except (TypeError, ValueError):
                    pass
    return int(z)


def filter_values(filt, tag):
    """Extrait les valeurs d'un tag dans un filtre MapLibre (récursif)."""
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
            if isinstance(vals, list) and vals[0] == "literal":
                return [str(v) for v in vals[1]]
            return [str(v) for v in filt[2:] if isinstance(v, str)]
    if op in ("any", "all"):
        out = []
        for sub in filt[1:]:
            out += filter_values(sub, tag)
        return out
    return []

# ── Analyse par groupe ────────────────────────────────────────────────────────

def analyse_group(name, style_layers):
    prefixes = GROUPS[name]
    matched  = [l for l in style_layers
                if any(l["id"].startswith(p) for p in prefixes)
                and l.get("source")]
    if not matched:
        return None

    # zoom min global du groupe
    zmins = [min_zoom_of(l) for l in matched]
    appear_at = min(zmins) if zmins else 10
    appear_at = max(appear_at, 10)  # minimum 10

    # couleur principale (première trouvée parmi les fills)
    main_color = None
    for l in matched:
        c = first_color(l.get("paint", {}))
        if c:
            main_color = c
            break

    # visibilité
    visible = not any(
        l.get("layout", {}).get("visibility") == "none"
        for l in matched
        if not l["id"].endswith("-3d")  # le layer 3d est hidden par défaut, ignorer
    )

    # sous-types : (valeur_tag → {color, appear_at})
    tag = LAYER_TAG.get(name, "type")
    subtypes = {}   # valeur → {color, appear_at}

    for l in matched:
        filt = l.get("filter")
        if not filt:
            continue
        vals = filter_values(filt, tag)
        lz   = min_zoom_of(l)
        lc   = first_color(l.get("paint", {}))
        for v in vals:
            if v not in subtypes:
                subtypes[v] = {}
            # couleur spécifique ?
            if lc and lc != main_color:
                subtypes[v]["color"] = lc
            # appear_at spécifique (si différent du groupe) ?
            if lz > appear_at:
                subtypes[v]["appear_at"] = lz

    # Nettoyer les sous-types vides
    subtypes = {k: v for k, v in subtypes.items() if v}

    return {
        "appear_at": appear_at,
        "main_color": main_color,
        "visible": visible,
        "subtypes": subtypes,
    }

# ── Sérialiseur YAML avec commentaires ───────────────────────────────────────

def dump_layer(name, info):
    """Retourne une chaîne YAML pour une couche, avec commentaires inline."""
    lines = []
    label  = LABELS.get(name, name.capitalize())
    appear = info["appear_at"]
    color  = info["main_color"]
    vis    = info["visible"]

    lines.append(f"  {name}:")
    lines.append(f"    label: {label}")
    if color:
        lines.append(f"    color: \"{color}\"")
    if not vis:
        lines.append(f"    visible: false")
    lines.append(f"    appear_at: {appear}")

    if info["subtypes"]:
        lines.append(f"    subtypes:")
        for val, scfg in sorted(info["subtypes"].items()):
            parts = []
            if "color" in scfg:
                parts.append(f"color: \"{scfg['color']}\"")
            if "appear_at" in scfg:
                parts.append(f"appear_at: {scfg['appear_at']}")
            inner = ", ".join(parts)
            lines.append(f"      {val}: {{ {inner} }}")

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

    style_layers = style.get("layers", [])
    print(f"→ {len(style_layers)} layers MapLibre lus depuis {style_path}")

    # Fond de carte
    bg = next((l["paint"].get("background-color", "#f2efe9")
               for l in style_layers if l.get("type") == "background"), "#f2efe9")
    glyphs = style.get("glyphs",
        "https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf")

    # Analyser chaque groupe
    groups_info = {}
    for name in GROUPS:
        info = analyse_group(name, style_layers)
        if info:
            groups_info[name] = info
            st_n = len(info["subtypes"])
            print(f"   {name:20s}  appear_at={info['appear_at']:2d}  "
                  f"color={info['main_color'] or '—':8s}  "
                  f"{st_n} sous-types")

    # ── Écrire le YAML ────────────────────────────────────────────────────────
    out_lines = [
        "# ──────────────────────────────────────────────────────────────────────",
        f"# map.config.yaml  —  généré depuis {style_path}  par retro_style.py",
        "#",
        "# Modifier CE fichier, pas style.json directement.",
        "# Regénérer avec :  python3 build_map.py",
        "# ──────────────────────────────────────────────────────────────────────",
        "",
        "map:",
        "  name: Map",
        "  center: [4.3517, 50.8503]",
        "  zoom: 13",
        f"  background: \"{bg}\"",
        "  font: \"#734a08\"",
        f"  glyphs: \"{glyphs}\"",
        "",
        "",
        "layers:",
        "",
    ]

    for name, info in groups_info.items():
        out_lines.append(dump_layer(name, info))
        out_lines.append("")

    out_path = Path(args.out)
    out_path.write_text("\n".join(out_lines))
    print(f"\n✓  {out_path}  ({len(groups_info)} couches)")
    print(f"\n→  Éditer {out_path}, puis :")
    print(f"   python3 build_map.py --config {out_path}")

if __name__ == "__main__":
    main()
