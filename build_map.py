#!/usr/bin/env python3
"""
build_map.py  —  map.config.yaml → style.json + granulometry.json + pmtiles_params.json
"""
import argparse, json, sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("✗  pip install pyyaml", file=sys.stderr); sys.exit(1)

# ── Helpers ───────────────────────────────────────────────────────────────────

COLORS = {"white":"#ffffff","black":"#000000","transparent":"rgba(0,0,0,0)"}

def c(v):
    if v is None: return None
    s = str(v).strip().lower()
    return COLORS.get(s, str(v))

def lc(layers, name):
    r = layers.get(name) or {}
    ap = r.get("appear_at", 10)
    return {
        "label":        r.get("label", name.capitalize()),
        "color":        c(r.get("color")),
        "border_color": c(r.get("border_color")),
        "visible":      r.get("visible", True),
        "appear_at":    ap,
        "labels_at":    r.get("labels_at", ap + 3),
        "opacity":      r.get("opacity", 1.0),
        "subtypes":     r.get("subtypes") or {},
        "extrusion_3d": r.get("extrusion_3d", False),
    }

def sc(cfg, key):
    """Config d'un sous-type avec tous les champs optionnels."""
    s = cfg["subtypes"].get(key) or {}
    return {
        "tag":           s.get("tag"),
        "color":         c(s.get("color", cfg["color"])),
        "color_private": c(s.get("color_private")),
        "pattern":       s.get("pattern"),
        "pattern_private": s.get("pattern_private"),
        "outline_color": c(s.get("outline_color")),
        "appear_at":     s.get("appear_at", cfg["appear_at"]),
        "opacity":       s.get("opacity",   cfg["opacity"]),
    }

def zoom(pairs):
    if len(pairs) == 1: return pairs[0][1]
    e = ["interpolate",["linear"],["zoom"]]
    for z,v in pairs: e += [z,v]
    return e

def color_or_case(col, col_private):
    """Retourne une expression MapLibre color ou case access=private."""
    if col_private:
        return ["case", ["==", ["get", "access"], "private"], col_private, col]
    return col


# ── LANDUSE ───────────────────────────────────────────────────────────────────

# Ordre de rendu des sous-types landuse : les zones "de fond" (larges,
# souvent étendues sur tout un quartier) sont dessinées en premier, les
# zones "d'inclusion" plus ponctuelles (brownfield, greenfield, allotments,
# garages, etc.) sont dessinées PAR-DESSUS, pour rester visibles même
# lorsqu'elles sont entièrement entourées par un grand polygone
# landuse=residential/industrial/... (suite issue #37).
LANDUSE_RENDER_ORDER = [
    # — fonds larges —
    "residential", "industrial", "commercial", "retail",
    "railway", "education", "farmland", "farmyard",
    # — inclusions ponctuelles, dessinées par-dessus —
    "brownfield", "greenfield", "construction", "landfill",
    "allotments", "cemetery", "garages", "depot", "quarry",
    "religious", "recreation_ground", "village_green", "military",
]

def landuse(cfg):
    out = []
    # Ordre explicite : fonds larges d'abord, inclusions ponctuelles
    # par-dessus. Les sous-types non listés (extensions futures du
    # config) sont ajoutés en dernier, par sécurité.
    order = [v for v in LANDUSE_RENDER_ORDER if v in cfg["subtypes"]]
    order += [v for v in cfg["subtypes"] if v not in order]

    for val in order:
        s = sc(cfg, val)
        if not s["color"]: continue
        tag = s["tag"] or "landuse"
        l = {"id": f"landuse-{val}", "type": "fill",
             "source": "landuse", "source-layer": "landuse",
             "filter": ["==", ["get", tag], val],
             "paint": {"fill-color": s["color"]}}
        if s["appear_at"] > 10: l["minzoom"] = s["appear_at"]
        if abs(s["opacity"] - 1.0) > 0.01: l["paint"]["fill-opacity"] = s["opacity"]
        out.append(l)
        # Pattern par-dessus (ex: military-hatch)
        if s["pattern"]:
            out.append({
                "id": f"landuse-{val}-hatch", "type": "fill",
                "source": "landuse", "source-layer": "landuse",
                "minzoom": s["appear_at"],
                "filter": ["==", ["get", tag], val],
                "paint": {"fill-pattern": s["pattern"]}
            })
        # Contour (ex: religious, quarry — façon osm-carto)
        if s["outline_color"]:
            ol = {"id": f"landuse-{val}-outline", "type": "line",
                  "source": "landuse", "source-layer": "landuse",
                  "filter": ["==", ["get", tag], val],
                  "paint": {"line-color": s["outline_color"], "line-width": 0.5}}
            if s["appear_at"] > 10: ol["minzoom"] = s["appear_at"]
            out.append(ol)
    return out


# ── GREEN ─────────────────────────────────────────────────────────────────────

# Ordre de rendu des sous-types green : "park" et "garden" sont souvent de
# grandes zones (parcs publics) qui CONTIENNENT des inclusions plus
# spécifiques (forêt, pelouse/meadow/grassland, lande, broussailles, massifs
# de fleurs). On dessine donc park/garden en premier (fond), puis les
# inclusions par-dessus, pour qu'elles restent visibles à l'intérieur d'un
# park.
FILTERS = {
    # — fonds (souvent de grandes zones, ex: parcs publics) —
    "park":      ["==", ["get","leisure"], "park"],
    "garden":    ["==", ["get","leisure"], "garden"],
    # — inclusions, dessinées par-dessus —
    "forest":    ["any", ["==",["get","landuse"],"forest"], ["==",["get","natural"],"wood"]],
    "scrub":     ["==", ["get","natural"], "scrub"],
    "shrubbery": ["==", ["get","natural"], "shrubbery"],
    "heath":     ["==", ["get","natural"], "heath"],
    # grass : couvre aussi natural=grassland (même rendu qu'osm-carto @grass)
    "grass":     ["any", ["==",["get","landuse"],"grass"],  ["==",["get","landuse"],"meadow"],
                          ["==",["get","natural"],"grassland"]],
    "flowerbed": ["==", ["get","landuse"], "flowerbed"],
    "wood":      None,  # couvert par forest
}

def green(cfg):
    out = []
    st = cfg["subtypes"]

    # Collecter les sous-types qui ont un pattern_private pour le layer composite
    hatch_vals = []

    for val, filt in FILTERS.items():
        if filt is None: continue   # wood couvert par forest
        s = sc(cfg, val)
        if not s["color"]: continue

        col_expr = color_or_case(s["color"], s["color_private"])
        l = {"id": f"green-{val}", "type": "fill",
             "source": "green", "source-layer": "green",
             "filter": filt,
             "paint": {"fill-color": col_expr}}
        if s["appear_at"] > 10: l["minzoom"] = s["appear_at"]
        if abs(s["opacity"] - 1.0) > 0.01: l["paint"]["fill-opacity"] = s["opacity"]
        out.append(l)

        if s["pattern_private"]:
            hatch_vals.append((val, s["pattern_private"], s["appear_at"]))

    # Layer pattern_private composite — un seul layer par pattern regroupant tous les sous-types
    from collections import defaultdict
    by_pattern = defaultdict(list)
    for val, pat, _ap in hatch_vals:
        by_pattern[pat].append(val)

    for pat, vals in by_pattern.items():
        tag_val_filters = []
        for val in vals:
            tag = (st.get(val) or {}).get("tag", "leisure")
            tag_val_filters.append(["==", ["get", tag], val])
        out.append({
            "id": f"green-hatch-{pat.replace('-','_')}", "type": "fill",
            "source": "green", "source-layer": "green",
            "filter": ["all", ["any"] + tag_val_filters,
                              ["==", ["get", "access"], "private"]],
            "paint": {"fill-pattern": pat}
        })

    return out


# ── WATER ─────────────────────────────────────────────────────────────────────

def water(cfg):
    col = cfg["color"] or "#aad3df"
    st  = cfg["subtypes"]
    out = []
    out.append({"id":"water-fill","type":"fill",
        "source":"water","source-layer":"water",
        "filter":["all",["!=",["get","tunnel"],"culvert"],
                        ["!=",["get","tunnel"],"yes"],
                        ["!=",["get","covered"],"yes"],
                        ["==",["geometry-type"],"Polygon"]],
        "paint":{"fill-color":col}})
    wetland = st.get("wetland") or {}
    out.append({"id":"water-wetland","type":"fill",
        "source":"water","source-layer":"water",
        "filter":["all",["==",["get","natural"],"wetland"],
                        ["==",["geometry-type"],"Polygon"]],
        "paint":{"fill-color": c(wetland.get("color","#d4e2c6")),
                 "fill-opacity": wetland.get("opacity", 0.5)}})
    # waterway=river/canal/stream/ditch : un tronçon en tunnel=culvert
    # doit avoir le MÊME rendu qu'un tronçon en tunnel=yes (hachuré, cf.
    # water-tunnel-casing/core ci-dessous, qui couvrent déjà yes ET
    # culvert) — on l'exclut donc ici pour éviter le double-rendu
    # (ligne pleine + hachures superposées).
    for ww,(w,dz) in {"river":([(10,1),(18,12)],10),"canal":([(10,1),(18,10)],10),
                       "stream":([(13,.5),(18,3)],13),"ditch":([(14,.3),(18,2)],14)}.items():
        az = (st.get(ww) or {}).get("appear_at", dz)
        out.append({"id":f"waterway-{ww}","type":"line",
            "source":"water","source-layer":"water","minzoom":az,
            "filter":["all",["==",["get","waterway"],ww],
                            ["!=",["get","tunnel"],"yes"],
                            ["!=",["get","tunnel"],"culvert"],
                            ["==",["geometry-type"],"LineString"]],
            "paint":{"line-color":col,"line-width":zoom(w)}})
    # Contour polygones eau + tunnels eau
    out.append({"id":"water-line","type":"line",
        "source":"water","source-layer":"water",
        "filter":["all",["!=",["get","tunnel"],"culvert"],["!=",["get","tunnel"],"yes"],
                        ["!=",["get","covered"],"yes"],["==",["geometry-type"],"Polygon"],
                        ["!",["has","waterway"]]],
        "paint":{"line-color":col,"line-width":zoom([(13,1),(18,10)])}})
    out.append({"id":"water-tunnel-casing","type":"line",
        "source":"water","source-layer":"water",
        "filter":["all",["any",["==",["get","tunnel"],"yes"],["==",["get","tunnel"],"culvert"]],
                        ["==",["geometry-type"],"LineString"]],
        "paint":{"line-color":col,"line-dasharray":[2,2],
                 "line-width":zoom([(13,1.5),(18,5)])}})
    out.append({"id":"water-tunnel-core","type":"line",
        "source":"water","source-layer":"water",
        "filter":["all",["any",["==",["get","tunnel"],"yes"],["==",["get","tunnel"],"culvert"]],
                        ["==",["geometry-type"],"LineString"]],
        "paint":{"line-color":"#e6faf9","line-opacity":0.4,
                 "line-width":zoom([(13,1),(18,4)])}})
    return out


# ── TREES ─────────────────────────────────────────────────────────────────────

def trees(cfg):
    col = cfg["color"] or "#6cae50"
    st  = cfg["subtypes"]
    ha  = (st.get("hedge")    or {}).get("appear_at", 14)
    ra  = (st.get("tree_row") or {}).get("appear_at", 15)
    ta  = (st.get("tree")     or {}).get("appear_at", 17)
    return [
        {"id":"trees-hedge","type":"line",
         "source":"trees","source-layer":"trees","minzoom":ha,
         "filter":["all",["==",["geometry-type"],"LineString"],["==",["get","barrier"],"hedge"]],
         "layout":{"line-cap":"round","line-join":"round"},
         "paint":{"line-color":"#6ba048","line-width":zoom([(ha,.8),(18,3.5)]),"line-opacity":0.85}},
        # tree_row : line de fond + symboles par leaf_type
        {"id":"trees-row-line","type":"line",
         "source":"trees","source-layer":"trees","minzoom":ra,
         "filter":["all",["==",["geometry-type"],"LineString"],["==",["get","natural"],"tree_row"]],
         "layout":{"line-cap":"round","line-join":"round"},
         "paint":{"line-color":"#8fbc77","line-wi
