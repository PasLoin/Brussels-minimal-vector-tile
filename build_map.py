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
    # layer=1) -> dalle plate fine flottant à une hauteur de
    # dégagement "raisonnable" plutôt que la boîte pleine par défaut.
    is_untagged_roof = ["all", is_roof, ["!", has_height_info]]

    normal_height_expr = ["case",
        ["has", "height"], ["to-number", ["get", "height"], 6],
        ["has", "building:levels"], ["+", base_expr,
            ["*", ["to-number", ["get", "building:levels"], 2], 3]],
        ["+", base_expr, 7.5]]

    # Différenciation visuelle des auvents/verrières (building=roof) :
    # un building=roof peut être posé exactement à la même position
    # qu'un AUTRE bâtiment OSM distinct en dessous (le vrai support,
    # souvent sans aucune hauteur taguée -> boîte pleine du sol par
    # défaut). Les deux features sont rendues CORRECTEMENT selon
    # leurs propres tags, mais avec la même couleur elles fusionnent
    # visuellement. fill-extrusion-color ACCEPTE les data expressions
    # (contrairement à fill-extrusion-opacity, qui ne supporte QUE des
    # expressions de zoom — la couleur seule porte donc toute la
    # différenciation, opacité fixe pour tous.
    roof_color = "#8a7d6c"

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
            "paint":{"fill-extrusion-color": ["case", is_roof, "#ff0000", col],
                     "fill-extrusion-base": ["case", is_roof, 50, base_expr],
                     "fill-extrusion-height": ["case", is_roof, 53, normal_height_expr],
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
    for k in st:
        s = sc(cfg, k)
        if s["color"]: fill_expr += [k, s["color"]]
    fill_expr.append(cfg["color"] or "#def3c0")

    # outline-color : match expression avec outline_color si défini
    outline_expr = ["match", ["get","leisure"]]
    has_custom_outline = False
    for k in st:
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


# ── ROADS ─────────────────────────────────────────────────────────────────────

def roads(cfg):
    st   = cfg["subtypes"]
    base = cfg["appear_at"]
    out  = []
    # man_made tunnel/bridge polygons
    for mm in ["tunnel","bridge"]:
        fc = "#adadad" if mm=="tunnel" else "#ffebee"
        op = 0.1 if mm=="tunnel" else 0.5
        out.append({"id":f"man_made-{mm}-fill","type":"fill",
            "source":"roads","source-layer":"roads",
            "filter":["all",["==",["get","man_made"],mm],["==",["geometry-type"],"Polygon"]],
            "layout":{"fill-sort-key":["coalesce",["to-number",["get","layer"]],0]},
            "paint":{"fill-color":fc,"fill-opacity":op}})
        dashed = {"line-dasharray":[2,2]} if mm=="tunnel" else {}
        out.append({"id":f"man_made-{mm}-outline","type":"line",
            "source":"roads","source-layer":"roads",
            "filter":["==",["get","man_made"],mm],
            "layout":{"line-join":"round","line-cap":"round",
                      "line-sort-key":["coalesce",["to-number",["get","layer"]],0]},
            "paint":{"line-color":"#ffc0cb" if mm=="tunnel" else "#adadad",
                     "line-width":2, **dashed}})
        if mm=="tunnel":
            out.append({"id":"man_made-tunnel-line-fill","type":"line",
                "source":"roads","source-layer":"roads",
                "filter":["all",["==",["get","man_made"],"tunnel"],
                                ["==",["geometry-type"],"LineString"]],
                "layout":{"line-join":"round","line-cap":"round",
                          "line-sort-key":["coalesce",["to-number",["get","layer"]],0]},
                "paint":{"line-color":"#adadad","line-opacity":.3,
                         "line-width":zoom([(14,2),(16,10),(18,20)])}})

    CLASSES = {
        "motorway":  (["motorway","motorway_link"],   "#dc2a67",[(5,1),(18,20)],  [(5,.5),(18,18)]),
        "trunk":     (["trunk","trunk_link"],          "#c84e2f",[(5,1),(18,18)],  [(5,.5),(18,16)]),
        "primary":   (["primary","primary_link"],      "#a06b00",[(7,1),(18,16)],  [(7,.5),(18,14)]),
        "secondary": (["secondary","secondary_link"],  "#707d05",[(9,1),(18,14)],  [(9,.5),(18,12)]),
        "tertiary":  (["tertiary","tertiary_link"],    "#8f8f8f",[(11,1),(18,12)], [(11,.5),(18,10)]),
        "local":     (["residential","unclassified",
                       "service","living_street"],     "#bbbbbb",[(13,1),(18,10)], [(13,.5),(18,8)]),
        "track":     (["track"],                       "#886622",[(13,.5),(18,3)], [(13,.5),(18,2)]),
        "busway":    (["busway"],                      "#bbbbbb",[(12,1.2),(18,11)],[(12,.8),(18,9)]),
    }
    for grp,(hw_vals,casing_c,cw,fw) in CLASSES.items():
        s   = st.get(grp) or {}
        ap  = s.get("appear_at", base)
        fc  = c(s.get("color", cfg["color"] or "#ffffff"))
        hwf = ["any"]+[["==",["get","highway"],v] for v in hw_vals]
        layout = {"line-cap":"round","line-join":"round",
                  "line-sort-key":["coalesce",["to-number",["get","layer"]],0]}
        for variant,extra,op in [("surface",["!=",["get","tunnel"],"yes"],1.0),
                                   ("tunnel", ["==",["get","tunnel"],"yes"],0.5)]:
            f = ["all",hwf,extra]
            out.append({"id":f"roads-casing-{grp}-{variant}","type":"line",
                "source":"roads","source-layer":"roads","minzoom":ap,
                "filter":f,"layout":layout,
                "paint":{"line-color":casing_c,"line-width":zoom(cw),"line-opacity":op,
                         **({"line-dasharray":[2,2]} if variant=="tunnel" else {})}})
            out.append({"id":f"roads-fill-{grp}-{variant}","type":"line",
                "source":"roads","source-layer":"roads","minzoom":ap,
                "filter":f,"layout":layout,
                "paint":{"line-color":fc,"line-width":zoom(fw),"line-opacity":op}})

    # busway center line
    busway_s = st.get("busway") or {}
    busway_ap = busway_s.get("appear_at", base)
    out.append({"id":"roads-center-busway","type":"line",
        "source":"roads","source-layer":"roads","minzoom":busway_ap,
        "filter":["==",["get","highway"],"busway"],
        "layout":{"line-cap":"butt","line-join":"round",
                  "line-sort-key":["coalesce",["to-number",["get","layer"]],0]},
        "paint":{"line-color":"#add19e","line-width":zoom([(busway_ap,.4),(18,2)]),
                 "line-dasharray":[2,2],
                 "line-opacity":["case",["==",["get","tunnel"],"yes"],.5,1.0]}})

    out.append({"id":"road-labels","type":"symbol",
        "source":"roads","source-layer":"roads","minzoom":cfg["labels_at"],
        "filter":["any"]+[["==",["get","highway"],v]
                          for v in ["primary","secondary","tertiary","residential"]],
        "layout":{"text-field":["get","name"],"text-font":["Noto Sans Regular"],
                  "text-size":11,"symbol-placement":"line","text-max-angle":30},
        "paint":{"text-color":"#333","text-halo-color":"rgba(255,255,255,0.6)",
                 "text-halo-width":1.5}})

    # ── Flèches de sens unique (issue #41) ──────────────────────────
    # oneway=yes -> flèche dans le sens du tracé de la géométrie.
    # oneway=-1 ignoré (déconseillé sur OSM, quasi absent des données).
    out.append({"id":"road-oneway-arrows","type":"symbol",
        "source":"roads","source-layer":"roads","minzoom":16,
        "filter":["==",["get","oneway"],"yes"],
        "layout":{
            "symbol-placement":"line",
            "symbol-spacing":zoom([(16,150),(18,80)]),
            "text-field":"→",
            "text-font":["Noto Sans Regular"],
            "text-size":zoom([(16,10),(18,14)]),
            "text-rotation-alignment":"map",
            "text-pitch-alignment":"map",
            "text-keep-upright":False,
            "text-allow-overlap":True,
            "text-ignore-placement":True},
        "paint":{"text-color":"#666666","text-opacity":0.7,
                 "text-halo-color":"rgba(255,255,255,0.6)","text-halo-width":1}})

    return out


# ── PEDESTRIAN ────────────────────────────────────────────────────────────────

def pedestrian(cfg):
    col = cfg["color"] or "#97644c"
    st  = cfg["subtypes"]
    DEFS = {
        "pedestrian_street":("pedestrian",13,None,  [(13,1.2),(18,6)],  False, "#999"),
        "pedestrian_fill":  ("pedestrian",13,None,  [(13,.8),(18,4)],   False, "#ededed"),
        "footway":          ("footway",   14,None,  [(14,.5),(18,1.5)], True,  col),
        "path":             ("path",      14,None,  [(14,.5),(18,1.5)], True,  col),
        "steps":            ("steps",     14,None,  [(14,1.5),(18,4)],  True,  col),
    }
    out = []
    # casing pour rue piétonne
    ap_ped = (st.get("pedestrian_street") or {}).get("appear_at", 13)
    out.append({"id":"pedestrian-street-casing","type":"line",
        "source":"pedestrian","source-layer":"pedestrian","minzoom":ap_ped,
        "filter":["==",["get","highway"],"pedestrian"],
        "layout":{"line-cap":"round","line-join":"round"},
        "paint":{"line-color":"#999","line-width":zoom([(ap_ped,1.2),(18,6)])}})
    out.append({"id":"pedestrian-street-fill","type":"line",
        "source":"pedestrian","source-layer":"pedestrian","minzoom":ap_ped,
        "filter":["==",["get","highway"],"pedestrian"],
        "layout":{"line-cap":"round","line-join":"round"},
        "paint":{"line-color":"#ededed","line-width":zoom([(ap_ped,.8),(18,4)])}})
    for key,(hw,dz,_,wp,dashed,lc_) in [
        ("footway",("footway",14,None,[(14,.5),(18,1.5)],True,col)),
        ("path",   ("path",   14,None,[(14,.5),(18,1.5)],True,col)),
        ("steps",  ("steps",  14,None,[(14,1.5),(18,4)], True,col)),
    ]:
        ap = (st.get(key) or {}).get("appear_at", dz)
        p  = {"line-color":lc_,"line-width":zoom(wp)}
        if dashed: p["line-dasharray"] = [2,2] if key!="steps" else [.2,.5]
        out.append({"id":f"pedestrian-{key}","type":"line",
            "source":"pedestrian","source-layer":"pedestrian","minzoom":ap,
            "filter":["==",["get","highway"],hw],"paint":p})
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


# ── Style complet ──────────────────────────────────────────────────────────────

SOURCES = ["landuse","roads","buildings","water","green","trees","boundaries",
           "poi","pedestrian","cycleway","railway","public_transport","leisure"]

def build_style(config):
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

    sources = {n:{"type":"vector","url":f"./{n}.pmtiles.gz",
                  "attribution":"© OpenStreetMap contributors"} for n in SOURCES}
    return {"version":8,"name":M.get("name","Map"),
            "sources":sources,"glyphs":gl,"layers":layers}


# ── Granulométrie ──────────────────────────────────────────────────────────────

ROAD_CLASSES = {
    "motorway": ["motorway","motorway_link"],
    "trunk":    ["trunk","trunk_link"],
    "primary":  ["primary","primary_link"],
    "secondary":["secondary","secondary_link"],
    "tertiary": ["tertiary","tertiary_link"],
    "local":    ["residential","unclassified","service","living_street"],
    "track":    ["track"],
    "busway":   ["busway"],
}
POI_PROPS = ["amenity","shop","tourism","name","name:fr","name:nl",
             "cuisine","opening_hours","addr:street","addr:housenumber","website","religion"]

def build_granulometry(config):
    L   = config.get("layers",{})
    out = {"_meta":{"generated_by":"build_map.py"},"layers":{}}
    for name, raw in L.items():
        raw  = raw or {}
        ap   = raw.get("appear_at", 10)
        st   = raw.get("subtypes") or {}
        rules = []
        if name == "roads":
            # "oneway" est dans LOW (issue #41) : toujours conservé dès
            # l'apparition de la route, pour permettre le rendu des
            # flèches de sens unique sur TOUTES les classes (y compris
            # primary/secondary/tertiary, dont gap+4 >= 18 → pas de tier
            # HIGH séparé). maxspeed/lanes/access restent réservés au
            # tier HIGH (haut zoom uniquement).
            LOW  = ["highway","name","ref","tunnel","bridge","layer","oneway"]
            HIGH = LOW + ["maxspeed","lanes","access"]
            for grp,hw_vals in ROAD_CLASSES.items():
                gap = (st.get(grp) or {}).get("appear_at", ap)
                if gap > 10:
                    rules.append({"match":{"highway":hw_vals},
                                  "zoom_min":10,"zoom_max":gap-1,"action":"drop"})
                mid = min(gap+4, 18)
                rules.append({"match":{"highway":hw_vals},
                              "zoom_min":gap,"zoom_max":mid,"keep_properties":LOW})
                if mid < 18:
                    rules.append({"match":{"highway":hw_vals},
                                  "zoom_min":mid+1,"zoom_max":18,"keep_properties":HIGH})
        elif name == "poi":
            for pt, scfg in st.items():
                scfg = scfg or {}
                pap  = scfg.get("appear_at", ap)
                tag  = scfg.get("tag","amenity")
                if pap > 10:
                    rules.append({"match":{tag:[pt]},"zoom_min":10,"zoom_max":pap-1,"action":"drop"})
                rules.append({"match":{tag:[pt]},"zoom_min":pap,"zoom_max":18,"keep_properties":POI_PROPS})
            if ap > 10:
                rules.append({"zoom_min":10,"zoom_max":ap-1,"action":"drop"})
            rules.append({"zoom_min":ap,"zoom_max":18,"keep_properties":POI_PROPS})
        else:
            if ap > 10:
                rules.append({"zoom_min":10,"zoom_max":ap-1,"action":"drop"})
            for stk, scfg in st.items():
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
