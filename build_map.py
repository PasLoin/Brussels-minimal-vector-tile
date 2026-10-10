#!/usr/bin/env python3
"""
build_map.py  —  map.config.yaml → style.json + granulometry.json + pmtiles_params.json
"""
import argparse, hashlib, json, sys
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
         "paint":{"line-color":"#8fbc77","line-width":zoom([(ra,.5),(18,1.5)]),"line-opacity":0.55}},
        {"id":"trees-row-broadleaved","type":"symbol",
         "source":"trees","source-layer":"trees","minzoom":ra+1,
         "filter":["all",["==",["geometry-type"],"LineString"],["==",["get","natural"],"tree_row"],
                         ["==",["get","leaf_type"],"broadleaved"]],
         "layout":{"symbol-placement":"line","symbol-spacing":zoom([(ra+1,48),(18,32)]),
                   "text-field":"●","text-font":["Noto Sans Regular"],
                   "text-size":zoom([(ra+1,9),(18,13)]),
                   "text-rotation-alignment":"map","text-allow-overlap":False},
         "paint":{"text-color":"#6cae50","text-halo-color":"#f2efe9","text-halo-width":.8}},
        {"id":"trees-row-needleleaved","type":"symbol",
         "source":"trees","source-layer":"trees","minzoom":ra+1,
         "filter":["all",["==",["geometry-type"],"LineString"],["==",["get","natural"],"tree_row"],
                         ["==",["get","leaf_type"],"needleleaved"]],
         "layout":{"symbol-placement":"line","symbol-spacing":zoom([(ra+1,48),(18,32)]),
                   "text-field":"▲","text-font":["Noto Sans Regular"],
                   "text-size":zoom([(ra+1,9),(18,13)]),
                   "text-rotation-alignment":"map","text-allow-overlap":False},
         "paint":{"text-color":"#5f9f50","text-halo-color":"#f2efe9","text-halo-width":.8}},
        {"id":"trees-row-default","type":"symbol",
         "source":"trees","source-layer":"trees","minzoom":ra+1,
         "filter":["all",["==",["geometry-type"],"LineString"],["==",["get","natural"],"tree_row"],
                         ["!",["in",["get","leaf_type"],["literal",["broadleaved","needleleaved"]]]]],
         "layout":{"symbol-placement":"line","symbol-spacing":zoom([(ra+1,48),(18,32)]),
                   "text-field":"●","text-font":["Noto Sans Regular"],
                   "text-size":zoom([(ra+1,8),(18,12)]),
                   "text-rotation-alignment":"map","text-allow-overlap":False},
         "paint":{"text-color":"#7eb36a","text-halo-color":"#f2efe9","text-halo-width":.8}},
        # Arbres individuels par leaf_type
        {"id":"trees-tree-broadleaved","type":"symbol",
         "source":"trees","source-layer":"trees","minzoom":ta,
         "filter":["all",["==",["geometry-type"],"Point"],["==",["get","natural"],"tree"],
                         ["==",["get","leaf_type"],"broadleaved"]],
         "layout":{"text-field":"●","text-font":["Noto Sans Regular"],
                   "text-size":zoom([(ta,10),(18,14)]),"text-allow-overlap":False},
         "paint":{"text-color":"#6cae50","text-halo-color":"#f2efe9","text-halo-width":.9}},
        {"id":"trees-tree-needleleaved","type":"symbol",
         "source":"trees","source-layer":"trees","minzoom":ta,
         "filter":["all",["==",["geometry-type"],"Point"],["==",["get","natural"],"tree"],
                         ["==",["get","leaf_type"],"needleleaved"]],
         "layout":{"text-field":"▲","text-font":["Noto Sans Regular"],
                   "text-size":zoom([(ta,10),(18,14)]),"text-allow-overlap":False},
         "paint":{"text-color":"#5f9f50","text-halo-color":"#f2efe9","text-halo-width":.9}},
        {"id":"trees-tree-default","type":"symbol",
         "source":"trees","source-layer":"trees","minzoom":ta,
         "filter":["all",["==",["geometry-type"],"Point"],["==",["get","natural"],"tree"],
                         ["!",["in",["get","leaf_type"],["literal",["broadleaved","needleleaved"]]]]],
         "layout":{"text-field":"●","text-font":["Noto Sans Regular"],
                   "text-size":zoom([(ta,9),(18,13)]),"text-allow-overlap":False},
         "paint":{"text-color":"#7eb36a","text-halo-color":"#f2efe9","text-halo-width":.9}},
    ]


# ── BUILDINGS ─────────────────────────────────────────────────────────────────

def buildings(cfg):
    col = cfg["color"] or "#fce1c5"
    bc  = cfg["border_color"] or "#d4a574"
    ap  = cfg["appear_at"]

    # Base de l'extrusion : 0 normalement, sauf bâtiment surélevé
    # (passage carrossable / allée vers l'intérieur d'îlot) taggé
    # directement min_height/building:min_level, sans building:part.
    base_expr = ["case",
        ["has", "min_height"], ["to-number", ["get", "min_height"], 0],
        ["has", "building:min_level"], ["*", ["to-number", ["get", "building:min_level"], 0], 3],
        0]

    # Le bâtiment porte-t-il une info de hauteur exploitable quelconque ?
    has_height_info = ["any",
        ["has", "height"], ["has", "min_height"],
        ["has", "building:levels"], ["has", "building:min_level"]]

    is_roof = ["==", ["get", "building"], "roof"]

    # building=roof sans AUCUNE info exploitable (souvent juste
    # layer=1) -> flotte au MINIMUM à la même hauteur que le fallback
    # générique d'un bâtiment simple sans données (base 0 + 7.5m),
    # plutôt qu'une valeur arbitrairement basse qui le plaque contre
    # le bâtiment support en dessous (confirmé visuellement : avant
    # ces changements, ce type d'auvent flottait correctement à
    # mi-hauteur du bâtiment, pas au sol).
    is_untagged_roof = ["all", is_roof, ["!", has_height_info]]

    normal_height_expr = ["case",
        ["has", "height"], ["to-number", ["get", "height"], 6],
        ["has", "building:levels"], ["+", base_expr,
            ["*", ["to-number", ["get", "building:levels"], 2], 3]],
        ["+", base_expr, 7.5]]

    # Différenciation visuelle des auvents/verrières (building=roof) :
    # un building=roof peut être posé exactement à la même position
    # qu'un AUTRE bâtiment OSM distinct en dessous (le vrai support).
    # Couleur nettement plus saturée que la teinte bâtiment standard
    # pour rester identifiable même proche en hauteur d'un volume
    # voisin — fill-extrusion-opacity ne supporte QUE des expressions
    # de zoom (pas de data expression), donc toute la différenciation
    # passe par la couleur.
    roof_color = "#6b4f3a"

    out = [{"id":"buildings-fill","type":"fill",
             "source":"buildings","source-layer":"buildings","minzoom":ap,
             "paint":{"fill-color":col}}]
    if cfg["extrusion_3d"]:
        out.append({"id":"buildings-3d","type":"fill-extrusion",
            "source":"buildings","source-layer":"buildings","minzoom":ap,
            "layout":{"visibility":"none"},
            # lod="detail" (issue z15-18 leak) : exclut explicitement
            # les features du palier fusionné (lod=merged, ajouté par
            # merge_buildings.py), au cas où tippecanoe en laisserait
            # fuiter au-delà de leur tranche de zoom prévue z10-12 —
            # filtre robuste, indépendant des réglages tippecanoe.
            # covered_by_parts!=yes (issue #40) : un bâtiment
            # entièrement recouvert par ses building:part (relation
            # explicite ou heuristique géométrique ≥90%, cf.
            # compute_building_coverage.py) ne doit pas être extrudé
            # ici, sous peine de silhouette dédoublée avec
            # building-parts-3d. Le rendu 2D (buildings-fill/
            # buildings-outline) reste inchangé pour tous les
            # bâtiments, quels que soient lod/covered_by_parts.
            "filter": ["all",
                ["==", ["get", "lod"], "detail"],
                ["!=", ["get", "covered_by_parts"], "yes"]],
            "paint":{"fill-extrusion-color": ["case", is_roof, roof_color, col],
                     "fill-extrusion-base": ["case", is_untagged_roof, 7.2, base_expr],
                     "fill-extrusion-height": ["case", is_untagged_roof, 7.5, normal_height_expr],
                     "fill-extrusion-opacity": 0.75}})
    out.append({"id":"buildings-outline","type":"line",
        "source":"buildings","source-layer":"buildings","minzoom":ap,
        "paint":{"line-color":bc,"line-width":.5}})
    return out

# ── LEISURE ───────────────────────────────────────────────────────────────────

def leisure(cfg):
    st = cfg["subtypes"]

    # fill-color : match expression avec couleurs par sous-type
    fill_expr = ["match", ["get","leisure"]]
    for k in sorted(st):
        s = sc(cfg, k)
        if s["color"]: fill_expr += [k, s["color"]]
    fill_expr.append(cfg["color"] or "#def3c0")

    # outline-color : match expression avec outline_color si défini
    outline_expr = ["match", ["get","leisure"]]
    has_custom_outline = False
    for k in sorted(st):
        s = sc(cfg, k)
        if s["outline_color"]:
            outline_expr += [k, s["outline_color"]]
            has_custom_outline = True
    outline_expr.append("#adadad")

    return [
        {"id":"leisure-fill","type":"fill",
         "source":"leisure","source-layer":"leisure",
         "filter":["==",["geometry-type"],"Polygon"],
         "paint":{"fill-color":fill_expr,"fill-opacity":1.0}},
        {"id":"leisure-outline","type":"line",
         "source":"leisure","source-layer":"leisure",
         "filter":["==",["geometry-type"],"Polygon"],
         "paint":{"line-color": outline_expr if has_custom_outline else "#adadad",
                  "line-width":.5}},
    ]


ROAD_ORDER = [
    "track", "service", "busway", "living_street", "unclassified", "residential",
    "tertiary_link", "secondary_link", "primary_link", "trunk_link", "motorway_link",
    "tertiary", "secondary", "primary", "trunk", "motorway",
]

ROAD_LEGACY_GROUP = {
    "motorway": "motorway", "motorway_link": "motorway",
    "trunk": "trunk",       "trunk_link": "trunk",
    "primary": "primary",   "primary_link": "primary",
    "secondary": "secondary", "secondary_link": "secondary",
    "tertiary": "tertiary", "tertiary_link": "tertiary",
    "residential": "local", "unclassified": "local",
    "service": "local",     "living_street": "local",
    "track": "track",       "busway": "busway",
}

_W_MAJOR  = [(10, 1.5), (13, 3.0), (15, 8.0), (18, 22.0)]
_W_PRIM   = [(10, 1.2), (13, 2.5), (15, 7.0), (18, 20.0)]
_W_SEC    = [(10, 1.0), (13, 2.5), (15, 7.0), (18, 18.0)]
_W_TERT   = [(11, 0.8), (13, 2.0), (15, 6.0), (18, 16.0)]
_W_LOCAL  = [(12, 0.6), (13, 1.2), (15, 4.5), (18, 14.0)]
_W_LIVING = [(13, 1.0), (15, 4.0), (18, 12.0)]
_W_LINK   = [(12, 0.8), (15, 4.0), (18, 12.0)]
_W_SERV   = [(14, 0.8), (16, 3.0), (18, 7.0)]
_W_BUS    = [(12, 0.8), (15, 3.0), (18, 9.0)]
_W_TRACK  = [(13, 0.6), (16, 1.5), (18, 2.5)]

ROAD_DEFAULTS = {
    "motorway":       ("#e892a2", "#dc2a67", 10, _W_MAJOR),
    "motorway_link":  ("#e892a2", "#dc2a67", 12, _W_LINK),
    "trunk":          ("#f9b29c", "#c84e2f", 10, _W_MAJOR),
    "trunk_link":     ("#f9b29c", "#c84e2f", 12, _W_LINK),
    "primary":        ("#fcd6a4", "#a06b00", 10, _W_PRIM),
    "primary_link":   ("#fcd6a4", "#a06b00", 12, _W_LINK),
    "secondary":      ("#f7fabf", "#707d05", 10, _W_SEC),
    "secondary_link": ("#f7fabf", "#707d05", 13, _W_LINK),
    "tertiary":       ("#ffffff", "#8f8f8f", 11, _W_TERT),
    "tertiary_link":  ("#ffffff", "#8f8f8f", 13, _W_LINK),
    "residential":    ("#ffffff", "#bbbbbb", 12, _W_LOCAL),
    "unclassified":   ("#ffffff", "#bbbbbb", 12, _W_LOCAL),
    "living_street":  ("#ededed", "#c6c6c6", 13, _W_LIVING),
    "service":        ("#ffffff", "#bbbbbb", 14, _W_SERV),
    "busway":         ("#ffffff", "#bbbbbb", 13, _W_BUS),
    "track":          ("#996600", None,      13, _W_TRACK),
}

ROAD_TUNNEL_VALUES = ["yes", "building_passage"]
ROAD_BUSWAY_CENTER = "#6699ff"
ROAD_BRIDGE_CASING = "#000000"
ROAD_LABEL_VALUES  = ["motorway", "trunk", "primary", "secondary", "tertiary",
                      "residential", "unclassified", "living_street"]


def road_subtype(cfg_or_layer, value):
    raw_st = cfg_or_layer.get("subtypes") or {}
    layer_ap = cfg_or_layer.get("appear_at", 10) or 10
    fill, casing, ap, widths = ROAD_DEFAULTS[value]
    legacy = raw_st.get(ROAD_LEGACY_GROUP.get(value)) or {}
    own    = raw_st.get(value) or {}
    merged = {**legacy, **own}
    return {
        "color":   c(merged.get("color", fill)),
        "casing":  c(merged.get("outline_color", casing)) if casing or "outline_color" in merged else None,
        "appear_at": int(merged.get("appear_at", max(ap, layer_ap))),
        "opacity": merged.get("opacity"),
        "widths":  widths,
    }


def _interp(stops, z):
    if z <= stops[0][0]:  return stops[0][1]
    if z >= stops[-1][0]: return stops[-1][1]
    for (z0, v0), (z1, v1) in zip(stops, stops[1:]):
        if z0 <= z <= z1:
            return round(v0 + (v1 - v0) * (z - z0) / (z1 - z0), 2)


def _curve_from(stops, ap):
    return [(ap, _interp(stops, ap))] + [(z, w) for z, w in stops if z > ap]


def _road_border(z):
    return 0.5 if z <= 13 else (1.0 if z <= 16 else 1.5)


def _casing_curve(fill_curve, factor=1.0):
    return [(z, round(w + 2 * _road_border(z) * factor, 2)) for z, w in fill_curve]


def _lighten(hex_col, amount=0.5):
    h = hex_col.lstrip("#")
    if len(h) == 3: h = "".join(ch * 2 for ch in h)
    if len(h) != 6: return hex_col
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    mix = lambda v: round(v + (255 - v) * amount)
    return "#{:02x}{:02x}{:02x}".format(mix(r), mix(g), mix(b))


def roads(cfg):
    out = []
    sort_key = ["coalesce", ["to-number", ["get", "layer"]], 0]

    for mm in ["tunnel", "bridge"]:
        fc = "#adadad" if mm == "tunnel" else "#ffebee"
        op = 0.1 if mm == "tunnel" else 0.5
        out.append({"id": f"man_made-{mm}-fill", "type": "fill",
            "source": "roads", "source-layer": "roads",
            "filter": ["all", ["==", ["get", "man_made"], mm], ["==", ["geometry-type"], "Polygon"]],
            "layout": {"fill-sort-key": sort_key},
            "paint": {"fill-color": fc, "fill-opacity": op}})
        dashed = {"line-dasharray": [2, 2]} if mm == "tunnel" else {}
        out.append({"id": f"man_made-{mm}-outline", "type": "line",
            "source": "roads", "source-layer": "roads",
            "filter": ["==", ["get", "man_made"], mm],
            "layout": {"line-join": "round", "line-cap": "round", "line-sort-key": sort_key},
            "paint": {"line-color": "#ffc0cb" if mm == "tunnel" else "#adadad",
                      "line-width": 2, **dashed}})
        if mm == "tunnel":
            out.append({"id": "man_made-tunnel-line-fill", "type": "line",
                "source": "roads", "source-layer": "roads",
                "filter": ["all", ["==", ["get", "man_made"], "tunnel"],
                                  ["==", ["geometry-type"], "LineString"]],
                "layout": {"line-join": "round", "line-cap": "round", "line-sort-key": sort_key},
                "paint": {"line-color": "#adadad", "line-opacity": .3,
                          "line-width": zoom([(14, 2), (16, 10), (18, 20)])}})

    is_tunnel = ["in", ["get", "tunnel"], ["literal", ROAD_TUNNEL_VALUES]]
    is_bridge = ["all", ["has", "bridge"], ["!=", ["get", "bridge"], "no"]]
    variants = {
        "tunnel":  is_tunnel,
        "surface": ["all", ["!", is_tunnel], ["!", is_bridge]],
        "bridge":  ["all", ["!", is_tunnel], is_bridge],
    }
    resolved = {v: road_subtype(cfg, v) for v in ROAD_ORDER}

    def layer(lid, hw, variant, paint, cap="round"):
        s = resolved[hw]
        return {"id": lid, "type": "line",
                "source": "roads", "source-layer": "roads",
                "minzoom": s["appear_at"],
                "filter": ["all", ["==", ["get", "highway"], hw], variants[variant]],
                "layout": {"line-cap": cap, "line-join": "round", "line-sort-key": sort_key},
                "paint": paint}

    def casing_pass(variant):
        for hw in ROAD_ORDER:
            s = resolved[hw]
            if not s["casing"]:
                continue
            fill_w = _curve_from(s["widths"], s["appear_at"])
            if variant == "bridge":
                col, w, extra = ROAD_BRIDGE_CASING, _casing_curve(fill_w, 1.6), {}
            elif variant == "tunnel":
                col, w, extra = s["casing"], _casing_curve(fill_w), {"line-dasharray": [2, 1]}
            else:
                col, w, extra = s["casing"], _casing_curve(fill_w), {}
            out.append(layer(f"roads-{variant}-casing-{hw}", hw, variant,
                             {"line-color": col, "line-width": zoom(w), **extra},
                             cap="butt" if variant != "surface" else "round"))

    def fill_pass(variant):
        for hw in ROAD_ORDER:
            s = resolved[hw]
            w = _curve_from(s["widths"], s["appear_at"])
            paint = {"line-color": _lighten(s["color"]) if variant == "tunnel" else s["color"],
                     "line-width": zoom(w)}
            if hw == "track":
                paint["line-dasharray"] = [3, 2]
            if variant != "tunnel" and s["opacity"] is not None \
                    and abs(float(s["opacity"]) - 1.0) > 0.01:
                paint["line-opacity"] = float(s["opacity"])
            out.append(layer(f"roads-{variant}-fill-{hw}", hw, variant, paint,
                             cap="butt" if hw == "track" else "round"))

    casing_pass("tunnel");  fill_pass("tunnel")
    casing_pass("surface"); fill_pass("surface")

    bap = resolved["busway"]["appear_at"]
    out.append({"id": "roads-center-busway", "type": "line",
        "source": "roads", "source-layer": "roads", "minzoom": bap,
        "filter": ["match", ["get", "highway"], ["busway"], True, False],
        "layout": {"line-cap": "butt", "line-join": "round", "line-sort-key": sort_key},
        "paint": {"line-color": ROAD_BUSWAY_CENTER,
                  "line-width": zoom(_curve_from([(12, .4), (18, 2)], bap)),
                  "line-dasharray": [2, 2]}})

    casing_pass("bridge");  fill_pass("bridge")

    out.append({"id": "road-labels", "type": "symbol",
        "source": "roads", "source-layer": "roads", "minzoom": cfg["labels_at"],
        "filter": ["match", ["get", "highway"], ROAD_LABEL_VALUES, True, False],
        "layout": {"text-field": ["get", "name"], "text-font": ["Noto Sans Regular"],
                   "text-size": zoom([(cfg["labels_at"], 10), (18, 13)]),
                   "symbol-placement": "line", "text-max-angle": 30},
        "paint": {"text-color": "#222222", "text-halo-color": "rgba(255,255,255,0.8)",
                  "text-halo-width": 1.5}})

    out.append({"id": "road-oneway-arrows", "type": "symbol",
        "source": "roads", "source-layer": "roads", "minzoom": 16,
        "filter": ["==", ["get", "oneway"], "yes"],
        "layout": {
            "symbol-placement": "line",
            "symbol-spacing": zoom([(16, 150), (18, 80)]),
            "text-field": "→",
            "text-font": ["Noto Sans Regular"],
            "text-size": zoom([(16, 10), (18, 14)]),
            "text-rotation-alignment": "map",
            "text-pitch-alignment": "map",
            "text-keep-upright": False,
            "text-allow-overlap": True,
            "text-ignore-placement": True},
        "paint": {"text-color": "#666666", "text-opacity": 0.7,
                  "text-halo-color": "rgba(255,255,255,0.6)", "text-halo-width": 1}})

    return out


# ── PEDESTRIAN ────────────────────────────────────────────────────────────────

FOOTWAY_NOACCESS = "#bbbbbb"
FOOTWAY_WIDTHS = [(14, 0.7), (15, 1.0), (16, 1.3), (18, 1.3), (19, 1.6)]
FOOTWAY_BACKGROUND = 2.0
FOOTWAY_DASH_Z14 = (1, 3)
FOOTWAY_DASHES = {
    "paved":   {15: (2, 3.5), 16: (3, 3.5), 17: (3, 3)},
    "unpaved": {15: (1, 4)},
    "unknown": {15: (1, 3, 2, 4), 16: (1, 4, 2, 3)},
}
SURFACE_PAVED = ["paved", "asphalt", "cobblestone", "cobblestone:flattened", "sett",
                 "unhewn_cobblestone", "concrete", "concrete:lanes", "concrete:plates",
                 "paving_stones", "metal", "wood"]
SURFACE_UNPAVED = ["unpaved", "compacted", "dirt", "earth", "fine_gravel", "grass",
                   "grass_paver", "gravel", "ground", "mud", "pebblestone", "salt",
                   "sand", "woodchips", "clay", "ice", "snow", "rock"]


def _footway_surface_filter(kind):
    paved = ["in", ["get", "surface"], ["literal", SURFACE_PAVED]]
    unpaved = ["in", ["get", "surface"], ["literal", SURFACE_UNPAVED]]
    if kind == "paved":
        return paved
    if kind == "unpaved":
        return unpaved
    return ["all", ["!", paved], ["!", unpaved]]


def _footway_noaccess():
    return ["any",
        ["in", ["get", "foot"], ["literal", ["no", "private"]]],
        ["all", ["in", ["get", "access"], ["literal", ["no", "private"]]],
                ["!", ["in", ["get", "foot"], ["literal", ["yes", "designated", "permissive", "destination"]]]]]]


def _footway_width_at(z):
    return _interp(FOOTWAY_WIDTHS, z)


def _footway_dasharray(kind):
    w14 = _footway_width_at(14)
    expr = ["step", ["zoom"], ["literal", [round(v / w14, 2) for v in FOOTWAY_DASH_Z14]]]
    for z, dash in sorted(FOOTWAY_DASHES[kind].items()):
        w = _footway_width_at(z)
        expr += [z, ["literal", [round(v / w, 2) for v in dash]]]
    return expr


def _footway_layers(key, s, ap):
    col = c(s.get("color", "#fa8072"))
    background = c(s.get("outline_color", "#ffffff"))
    hw = ["==", ["get", "highway"], key]
    visible = ["any", [">=", ["zoom"], 15], ["!", _footway_noaccess()]]
    bz = max(ap, 15)
    out = [{"id": f"pedestrian-{key}-casing", "type": "line",
        "source": "pedestrian", "source-layer": "pedestrian", "minzoom": bz,
        "filter": hw,
        "layout": {"line-cap": "round", "line-join": "round"},
        "paint": {"line-color": background, "line-opacity": 0.4,
                  "line-width": zoom([(z, round(w + FOOTWAY_BACKGROUND, 2))
                                      for z, w in _curve_from(FOOTWAY_WIDTHS, bz)])}}]
    for kind in ("paved", "unpaved", "unknown"):
        out.append({"id": f"pedestrian-{key}-{kind}", "type": "line",
            "source": "pedestrian", "source-layer": "pedestrian", "minzoom": ap,
            "filter": ["all", hw, _footway_surface_filter(kind), visible],
            "layout": {"line-cap": "round", "line-join": "round"},
            "paint": {"line-color": ["case", _footway_noaccess(), FOOTWAY_NOACCESS, col],
                      "line-width": zoom(_curve_from(FOOTWAY_WIDTHS, ap)),
                      "line-dasharray": _footway_dasharray(kind)}})
    return out


def pedestrian(cfg):
    col = cfg["color"] or "#97644c"
    st  = cfg["subtypes"]
    ped = {**(st.get("pedestrian_street") or {}), **(st.get("pedestrian") or {})}
    ap_ped = ped.get("appear_at", 13)
    ped_fill = c(ped.get("color", "#ededed"))
    ped_casing = c(ped.get("outline_color", "#999"))
    out = []
    out.append({"id":"pedestrian-street-casing","type":"line",
        "source":"pedestrian","source-layer":"pedestrian","minzoom":ap_ped,
        "filter":["==",["get","highway"],"pedestrian"],
        "layout":{"line-cap":"round","line-join":"round"},
        "paint":{"line-color":ped_casing,"line-width":zoom([(ap_ped,1.2),(18,6)])}})
    out.append({"id":"pedestrian-street-fill","type":"line",
        "source":"pedestrian","source-layer":"pedestrian","minzoom":ap_ped,
        "filter":["==",["get","highway"],"pedestrian"],
        "layout":{"line-cap":"round","line-join":"round"},
        "paint":{"line-color":ped_fill,"line-width":zoom([(ap_ped,.8),(18,4)])}})
    for key in ("footway", "path"):
        s = st.get(key) or {}
        out += _footway_layers(key, s, s.get("appear_at", 14))
    s  = st.get("steps") or {}
    ap = s.get("appear_at", 14)
    out.append({"id":"pedestrian-steps","type":"line",
        "source":"pedestrian","source-layer":"pedestrian","minzoom":ap,
        "filter":["==",["get","highway"],"steps"],
        "paint":{"line-color":c(s.get("color", col)),"line-width":zoom([(14,1.5),(18,4)]),
                 "line-dasharray":[.2,.5]}})
    return out


# ── CYCLEWAY ──────────────────────────────────────────────────────────────────

def cycleway(cfg):
    col = cfg["color"] or "#0000ff"
    out = [{"id":"cycleway","type":"line",
        "source":"cycleway","source-layer":"cycleway","minzoom":cfg["appear_at"],
        "paint":{"line-color":col,
                 "line-width":zoom([(cfg["appear_at"],.8),(18,2)]),
                 "line-dasharray":[3,3]}}]

    # ── Flèches de sens unique sur pistes cyclables (issue #41) ──────
    # oneway=yes -> piste à sens unique : flèche dans le sens du tracé.
    # Pas de flèche -> bidirectionnelle (convention standard).
    # "oneway" est déjà conservé par apply_granulometry (couche
    # cycleway sans sous-types -> keep_properties: "ALL").
    #
    # Rendu : flèche blanche + halo dans la couleur de la piste, plutôt
    # que flèche colorée semi-transparente (invisible sur la ligne
    # bleue en pointillés de même couleur).
    out.append({"id":"cycleway-oneway-arrows","type":"symbol",
        "source":"cycleway","source-layer":"cycleway","minzoom":16,
        "filter":["==",["get","oneway"],"yes"],
        "layout":{
            "symbol-placement":"line",
            "symbol-spacing":zoom([(16,100),(18,60)]),
            "text-field":"→",
            "text-font":["Noto Sans Regular"],
            "text-size":zoom([(16,10),(18,13)]),
            "text-rotation-alignment":"map",
            "text-pitch-alignment":"map",
            "text-keep-upright":False,
            "text-allow-overlap":True,
            "text-ignore-placement":True},
        "paint":{"text-color":"#ffffff","text-opacity":0.95,
                 "text-halo-color":col,"text-halo-width":1.5}})

    return out


# ── RAILWAY ───────────────────────────────────────────────────────────────────

def railway(cfg):
    st  = cfg["subtypes"]
    out = []
    DEFS = {
        "rail":      ([(10,2),(18,7)],[(10,.8),(18,2)],10),
        "subway":    (None,           [(12,.8),(18,2)],12),
        "tram":      (None,           [(13,.5),(18,1.5)],13),
        "miniature": (None,           [(14,.3),(18,1)],14),
    }
    # Tunnels
    for rw in ["rail","subway","tram"]:
        s   = st.get(rw) or {}
        col = c(s.get("color"))
        if not col: continue
        ap  = s.get("appear_at", DEFS[rw][2])
        filt_t = ["all",["==",["get","railway"],rw],
                        ["any",["==",["get","tunnel"],"yes"],
                               ["==",["get","tunnel"],"building_passage"]]]
        if rw == "rail":
            out += [
                {"id":f"railway-tunnel-{rw}-casing","type":"line",
                 "source":"railway","source-layer":"railway","minzoom":ap,"filter":filt_t,
                 "layout":{"line-join":"round"},
                 "paint":{"line-color":"#c0c0c0","line-width":zoom([(ap,3),(18,7)]),
                          "line-dasharray":[.2,4],"line-opacity":.4}},
                {"id":f"railway-tunnel-{rw}-core","type":"line",
                 "source":"railway","source-layer":"railway","minzoom":ap,"filter":filt_t,
                 "layout":{"line-join":"round"},
                 "paint":{"line-color":"#c0c0c0","line-width":zoom([(ap,.8),(18,2)]),
                          "line-dasharray":[5,3],"line-opacity":.5}},
            ]
        else:
            out.append({"id":f"railway-tunnel-{rw}","type":"line",
                "source":"railway","source-layer":"railway","minzoom":ap,"filter":filt_t,
                "layout":{"line-join":"round"},
                "paint":{"line-color":"#b0b0b0","line-width":zoom(DEFS[rw][1]),
                         "line-dasharray":[5,3],"line-opacity":.4 if rw=="tram" else .5}})

    # Surface + ponts
    for rw,(ties_w,core_w,dz) in DEFS.items():
        s   = st.get(rw) or {}
        col = c(s.get("color"))
        ap  = s.get("appear_at", dz)
        if not col: continue
        filt_s = ["all",["==",["get","railway"],rw],
                        ["!=",["get","tunnel"],"yes"],
                        ["!=",["get","tunnel"],"building_passage"],
                        ["!=",["get","bridge"],"yes"]]
        filt_b = ["all",["==",["get","railway"],rw],["==",["get","bridge"],"yes"]]

        if ties_w:
            for suffix, filt in [("",filt_s),("-bridge",filt_b)]:
                if suffix == "-bridge":
                    out.append({"id":f"railway-bridge-casing","type":"line",
                        "source":"railway","source-layer":"railway","minzoom":ap,
                        "filter":["all",["any"]+[["==",["get","railway"],r]
                                                  for r in ["rail","tram","subway"]],
                                        ["==",["get","bridge"],"yes"]],
                        "layout":{"line-join":"round"},
                        "paint":{"line-color":"#000000","line-width":zoom([(ap,4),(18,9)]),
                                 "line-opacity":.15}})
                out.append({"id":f"railway-{rw}{suffix}-ties","type":"line",
                    "source":"railway","source-layer":"railway","minzoom":ap,"filter":filt,
                    "layout":{"line-join":"round"},
                    "paint":{"line-color":col,"line-width":zoom(ties_w),"line-dasharray":[.2,4]}})
                out.append({"id":f"railway-{rw}{suffix}-core","type":"line",
                    "source":"railway","source-layer":"railway","minzoom":ap,"filter":filt,
                    "layout":{"line-join":"round"},
                    "paint":{"line-color":col,"line-width":zoom(core_w)}})
        else:
            for suffix, filt in [("",filt_s),("-bridge",filt_b)]:
                out.append({"id":f"railway-{rw}{suffix}","type":"line",
                    "source":"railway","source-layer":"railway","minzoom":ap,"filter":filt,
                    "layout":{"line-join":"round"},
                    "paint":{"line-color":col,"line-width":zoom(core_w)}})
    return out


# ── PUBLIC TRANSPORT ──────────────────────────────────────────────────────────

def public_transport(cfg):
    col = cfg["color"] or "#e3004f"
    ap  = cfg["appear_at"]
    la  = cfg["labels_at"]
    return [
        {"id":"public_transport-casing","type":"line",
         "source":"public_transport","source-layer":"public_transport","minzoom":ap,
         "layout":{"line-join":"round","line-cap":"round"},
         "paint":{"line-color":"#ffffff","line-width":zoom([(ap,3),(18,9)]),"line-opacity":.6}},
        {"id":"public_transport-line","type":"line",
         "source":"public_transport","source-layer":"public_transport","minzoom":ap,
         "layout":{"line-join":"round","line-cap":"round"},
         "paint":{"line-color":["coalesce",["get","colour"],col],
                  "line-width":zoom([(ap,1.5),(18,5)]),"line-opacity":.85}},
        {"id":"public_transport-label","type":"symbol",
         "source":"public_transport","source-layer":"public_transport","minzoom":la,
         "layout":{"text-field":["get","ref"],"text-font":["Noto Sans Regular"],
                   "text-size":11,"symbol-placement":"line","text-max-angle":30},
         "paint":{"text-color":["coalesce",["get","colour:text"],"#000000"],
                  "text-halo-color":"rgba(255,255,255,0.85)","text-halo-width":1.5}},
    ]


# ── BOUNDARIES ────────────────────────────────────────────────────────────────

def boundaries(cfg):
    return [{"id":"boundaries","type":"line",
        "source":"boundaries","source-layer":"boundaries","minzoom":cfg["appear_at"],
        "paint":{"line-color":cfg["color"] or "#ac46ac","line-width":1,
                 "line-dasharray":[5,5],"line-opacity":.7}}]


# ── POI ───────────────────────────────────────────────────────────────────────

def poi(cfg):
    fc = cfg["color"] or "#734a08"
    ap = cfg["appear_at"]
    la = cfg["labels_at"]
    return [
        {"id":"poi-circle","type":"circle",
         "source":"poi","source-layer":"poi","minzoom":ap,
         "paint":{"circle-radius":zoom([(ap,2),(18,4)]),"circle-color":fc,
                  "circle-stroke-color":"#fff","circle-stroke-width":.8,
                  "circle-opacity":.85}},
        {"id":"poi-icon","type":"symbol",
         "source":"poi","source-layer":"poi","minzoom":ap,
         "layout":{
             "icon-image":["coalesce",
                 ["case",["==",["get","cuisine"],"friture"],
                         ["image","poi-cuisine-friture"],["image",""]],
                 ["image",["concat","poi-",["get","shop"]]],
                 ["image",["concat","poi-",["get","amenity"]]],
                 ["image",["concat","poi-",["get","tourism"]]],
                 ["case",["has","shop"],["image","poi-shop"],["image",""]]],
             "icon-size":zoom([(ap,.7),(18,1.0)]),
             "icon-allow-overlap":True,"icon-padding":2,"icon-anchor":"center",
             "text-field":["step",["zoom"],"",la,["get","name"]],
             "text-font":["Noto Sans Regular"],"text-size":10,
             "text-offset":[0,1.2],"text-anchor":"top","text-optional":True},
         "paint":{"icon-opacity":.9,"text-color":fc,
                  "text-halo-color":"rgba(255,255,255,0.8)","text-halo-width":1.2}},
        # leisure-icon (POI sur source leisure)
        {"id":"leisure-icon","type":"symbol",
         "source":"leisure","source-layer":"leisure","minzoom":ap,
         "filter":["!=",["get","leisure"],"playground"],
         "layout":{
             "icon-padding":50,"symbol-placement":"point","icon-allow-overlap":False,
             "icon-image":["coalesce",
                 ["case",["==",["get","cuisine"],"friture"],
                         ["image","poi-cuisine-friture"],["image",""]],
                 ["image",["concat","poi-",["get","shop"]]],
                 ["image",["concat","poi-",["get","amenity"]]],
                 ["image",["concat","poi-",["get","tourism"]]],
                 ["case",["has","shop"],["image","poi-shop"],["image",""]]],
             "icon-size":zoom([(ap,.7),(18,1.0)]),
             "icon-ignore-placement":False,"icon-anchor":"center",
             "text-field":["step",["zoom"],"",la,["get","name"]],
             "text-font":["Noto Sans Regular"],"text-size":10,
             "text-offset":[0,1.2],"text-anchor":"top","text-optional":True},
         "paint":{"icon-opacity":.9,"text-color":fc,
                  "text-halo-color":"rgba(255,255,255,0.8)","text-halo-width":1.2}},
    ]


# ── STREET FURNITURE (mobilier urbain, issue #51) ─────────────────────────────
#
# bench, lounger, waste_basket, vending_machine (amenity) ; bollard,
# gate, bus_trap, cycle_barrier, lift_gate, planter, fence (barrier) ;
# street_lamp (highway) ; entrance=* (toute valeur). Géométrie mixte :
# Point pour tout sauf barrier=fence qui reste une LineString (même
# principe que trees.json : tree=Point, tree_row/hedge=LineString).
#
# L'expression icon-image ci-dessous est un FALLBACK statique : comme
# pour poi-icon/leisure-icon, www/poi_icons.js la regénère au chargement
# depuis www/poi-icons.json (_meta.type_keys/special_cases), construits
# par generate_poi_icons.py à partir de poi.json ET street_furniture.json
# fusionnés — aucune modification de poi_icons.js n'est nécessaire pour
# ajouter un nouveau type, seulement de generate_poi_icons.py / map.config.yaml.
def street_furniture_point_filter(st):
    by_tag = {}
    for val, scfg in st.items():
        tag = (scfg or {}).get("tag") or "amenity"
        by_tag.setdefault(tag, []).append(val)
    clauses = []
    for tag in sorted(by_tag):
        vals = sorted(by_tag[tag])
        if vals == [tag]:
            clauses.append(["has", tag])
        else:
            clauses.append(["in", ["get", tag], ["literal", vals]])
    point = ["==", ["geometry-type"], "Point"]
    if not clauses:
        return point
    return ["all", point, ["any"] + clauses]


def street_furniture(cfg):
    st    = cfg["subtypes"]
    ap    = cfg["appear_at"]
    fence_color = c((st.get("fence") or {}).get("color") or "#9c9c9c")

    icon_expr = ["coalesce",
        ["case",["has","vending"],
                ["image",["concat","poi-vending-",["get","vending"]]],["image",""]],
        ["case",["has","door"],
                ["image",["concat","poi-door-",["get","door"]]],["image",""]],
        ["image",["concat","poi-",["get","amenity"]]],
        ["image",["concat","poi-",["get","barrier"]]],
        ["case",["==",["get","highway"],"street_lamp"],
                ["image","poi-street_lamp"],["image",""]],
        ["case",["has","entrance"],["image","poi-entrance"],["image",""]]]

    out = []
    if "fence" in st:
        out.append({"id":"street-furniture-fence","type":"line",
            "source":"street_furniture","source-layer":"street_furniture",
            "minzoom":ap,
            "filter":["all",["==",["get","barrier"],"fence"],
                            ["==",["geometry-type"],"LineString"]],
            "paint":{"line-color":fence_color,
                     "line-width":zoom([(ap,.5),(18,1.5)]),"line-opacity":.8}})
    out.append({"id":"street-furniture-icon","type":"symbol",
        "source":"street_furniture","source-layer":"street_furniture",
        "minzoom":ap,
        "filter":street_furniture_point_filter(st),
        "layout":{"icon-image":icon_expr,
                  "icon-size":zoom([(ap,.7),(18,1.0)]),
                  "icon-allow-overlap":False,"icon-padding":2,
                  "icon-anchor":"center"},
        "paint":{"icon-opacity":.9}})
    return out


DEFAULT_SUBTYPES = {
    "water": {
        "river":  {"tag": "waterway", "appear_at": 10},
        "canal":  {"tag": "waterway", "appear_at": 10},
        "stream": {"tag": "waterway", "appear_at": 13},
        "ditch":  {"tag": "waterway", "appear_at": 14},
    },
    "trees": {
        "hedge":    {"tag": "barrier", "appear_at": 14},
        "tree_row": {"tag": "natural", "appear_at": 15},
        "tree":     {"tag": "natural", "appear_at": 17},
    },
    "pedestrian": {
        "pedestrian": {"tag": "highway", "appear_at": 13},
        "footway":    {"tag": "highway", "appear_at": 14},
        "path":       {"tag": "highway", "appear_at": 14},
        "steps":      {"tag": "highway", "appear_at": 14},
    },
    "railway": {
        "rail":      {"tag": "railway", "appear_at": 10},
        "subway":    {"tag": "railway", "appear_at": 12},
        "tram":      {"tag": "railway", "appear_at": 13},
        "miniature": {"tag": "railway", "appear_at": 14},
    },
}


def with_default_subtypes(config):
    layers = dict(config.get("layers") or {})
    for name, defaults in DEFAULT_SUBTYPES.items():
        raw = dict(layers.get(name) or {})
        st = {k: dict(v or {}) for k, v in (raw.get("subtypes") or {}).items()}
        for key, dflt in defaults.items():
            if key == "pedestrian" and "pedestrian_street" in st and "pedestrian" not in st:
                st["pedestrian"] = dict(st["pedestrian_street"])
            st[key] = {**dflt, **(st.get(key) or {})}
        raw["subtypes"] = st
        layers[name] = raw
    return {**config, "layers": layers}


# ── Style complet ──────────────────────────────────────────────────────────────

SOURCES = ["landuse","roads","buildings","water","green","trees","boundaries",
           "poi","pedestrian","cycleway","railway","public_transport","leisure",
           "street_furniture"]

def build_style(config):
    source_hash = config_hash(config)
    config = with_default_subtypes(config)
    L  = config.get("layers",{})
    M  = config.get("map",{})
    bgc = c(M.get("background","#f2efe9"))
    gl  = M.get("glyphs",
        "https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf")

    layers = [{"id":"background","type":"background","paint":{"background-color":bgc}}]
    layers += landuse(lc(L,"landuse"))
    layers += green(lc(L,"green"))
    layers += water(lc(L,"water"))
    layers += leisure(lc(L,"leisure"))
    layers += buildings(lc(L,"buildings"))
    layers += trees(lc(L,"trees"))
    layers += railway(lc(L,"railway"))
    layers += public_transport(lc(L,"public_transport"))
    layers += roads(lc(L,"roads"))
    layers += pedestrian(lc(L,"pedestrian"))
    layers += cycleway(lc(L,"cycleway"))
    layers += boundaries(lc(L,"boundaries"))
    layers += poi(lc(L,"poi"))
    layers += street_furniture(lc(L,"street_furniture"))

    sources = {n:{"type":"vector","url":f"./{n}.pmtiles.gz",
                  "attribution":"© OpenStreetMap contributors"} for n in SOURCES}
    meta_map = {k: M[k] for k in ("name","version","center","zoom","background","font","glyphs") if k in M}
    return {"version":8,"name":M.get("name","Map"),
            "metadata":{"brussels:map":meta_map,
                        "brussels:config_hash":source_hash},
            "sources":sources,"glyphs":gl,"layers":layers}


def config_hash(config):
    canon = json.dumps(config, sort_keys=True, ensure_ascii=False, separators=(",",":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12]


# ── Granulométrie ──────────────────────────────────────────────────────────────

SUBTYPE_ONLY_LAYERS = {"landuse", "trees", "railway", "pedestrian"}

POI_PROPS = ["amenity","shop","tourism","craft","office","healthcare","leisure","historic",
             "name","name:fr","name:nl",
             "cuisine","opening_hours","addr:street","addr:housenumber","website","religion"]

def build_granulometry(config):
    config = with_default_subtypes(config)
    L   = config.get("layers",{})
    out = {"_meta":{"generated_by":"build_map.py"},"layers":{}}
    names = list(L) + [n for n in SOURCES if n not in L]
    for name in names:
        raw  = L.get(name) or {}
        ap   = raw.get("appear_at", 10)
        st   = raw.get("subtypes") or {}
        rules = []
        if name == "roads":
            LOW  = ["highway","name","ref","tunnel","bridge","layer","oneway"]
            HIGH = LOW + ["maxspeed","lanes","access"]
            for hw in ROAD_ORDER:
                gap = road_subtype(raw, hw)["appear_at"]
                if gap > 10:
                    rules.append({"match":{"highway":[hw]},
                                  "zoom_min":10,"zoom_max":gap-1,"action":"drop"})
                mid = min(gap+4, 18)
                rules.append({"match":{"highway":[hw]},
                              "zoom_min":gap,"zoom_max":mid,"keep_properties":LOW})
                if mid < 18:
                    rules.append({"match":{"highway":[hw]},
                                  "zoom_min":mid+1,"zoom_max":18,"keep_properties":HIGH})
            rules.append({"match":{"man_made":["bridge","tunnel"]},
                          "zoom_min":10,"zoom_max":18,
                          "keep_properties":["man_made","name","layer","bridge","tunnel"]})
        elif name == "poi":
            for pt, scfg in sorted(st.items()):
                scfg = scfg or {}
                pap  = scfg.get("appear_at", ap)
                tag  = scfg.get("tag","amenity")
                if pap > 10:
                    rules.append({"match":{tag:[pt]},"zoom_min":10,"zoom_max":pap-1,"action":"drop"})
                rules.append({"match":{tag:[pt]},"zoom_min":pap,"zoom_max":18,"keep_properties":POI_PROPS})
            if ap > 10:
                rules.append({"zoom_min":10,"zoom_max":ap-1,"action":"drop"})
            rules.append({"zoom_min":ap,"zoom_max":18,"keep_properties":POI_PROPS})
        elif name in SUBTYPE_ONLY_LAYERS and st:
            for stk, scfg in sorted(st.items()):
                scfg = scfg or {}
                sap  = scfg.get("appear_at", ap)
                tag  = scfg.get("tag", name)
                if sap > 10:
                    rules.append({"match":{tag:[stk]},"zoom_min":10,"zoom_max":sap-1,"action":"drop"})
                rules.append({"match":{tag:[stk]},"zoom_min":sap,"zoom_max":18,"keep_properties":"ALL"})
            rules.append({"zoom_min":10,"zoom_max":18,"action":"drop"})
        else:
            if ap > 10:
                rules.append({"zoom_min":10,"zoom_max":ap-1,"action":"drop"})
            for stk, scfg in sorted(st.items()):
                scfg = scfg or {}
                sap  = scfg.get("appear_at", ap)
                tag  = scfg.get("tag", name)
                if sap > ap:
                    rules.append({"match":{tag:[stk]},"zoom_min":ap,"zoom_max":sap-1,"action":"drop"})
            rules.append({"zoom_min":ap,"zoom_max":18,"keep_properties":"ALL"})
        out["layers"][name] = {"rules":rules}
    return out


def build_pmtiles_params(config):
    L   = config.get("layers",{})
    out = {}
    for name, raw in L.items():
        raw  = raw or {}
        ap   = raw.get("appear_at", 10)
        st   = raw.get("subtypes") or {}
        first = min([ap]+[(s or {}).get("appear_at", ap) for s in st.values()])
        out[name] = {"zoom_min":10,"zoom_max":18,"first_visible":first}
    return out


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config",      default="map.config.yaml")
    p.add_argument("--style-out",   default="www/style.json")
    p.add_argument("--gran-out",    default="granulometry.json")
    p.add_argument("--pmtiles-out", default="pmtiles_params.json")
    p.add_argument("--only", choices=["style","granulometry","pmtiles"], default=None)
    args = p.parse_args()
    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"✗  {cfg_path} introuvable", file=sys.stderr); sys.exit(1)
    with open(cfg_path) as f:
        config = yaml.safe_load(f)
    print(f"→ {cfg_path}  ({len(config.get('layers',{}))} couches)")
    only = args.only
    if only in (None,"style"):
        s = build_style(config)
        Path(args.style_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.style_out).write_text(json.dumps(s,indent=2,ensure_ascii=False))
        print(f"✓  {args.style_out}  ({len(s['layers'])} layers MapLibre)")
    if only in (None,"granulometry"):
        g = build_granulometry(config)
        Path(args.gran_out).write_text(json.dumps(g,indent=2,ensure_ascii=False))
        print(f"✓  {args.gran_out}  ({sum(len(v['rules']) for v in g['layers'].values())} règles)")
    if only in (None,"pmtiles"):
        pm = build_pmtiles_params(config)
        Path(args.pmtiles_out).write_text(json.dumps(pm,indent=2,ensure_ascii=False))
        print(f"✓  {args.pmtiles_out}")
    if only is None:
        print("\nSuite :")
        for s in ["bash generate_json.bash","python3 apply_granulometry.py","bash generate_pmtiles.bash"]:
            print(f"   {s}")

if __name__ == "__main__":
    main()
