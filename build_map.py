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
    """Config d'un sous-type. Le champ 'tag' est préservé tel quel."""
    s = cfg["subtypes"].get(key) or {}
    return {
        "tag":      s.get("tag"),
        "color":    c(s.get("color", cfg["color"])),
        "appear_at":s.get("appear_at", cfg["appear_at"]),
        "opacity":  s.get("opacity",   cfg["opacity"]),
    }

def zoom(pairs):
    if len(pairs) == 1: return pairs[0][1]
    e = ["interpolate",["linear"],["zoom"]]
    for z,v in pairs: e += [z,v]
    return e


# ── Couche LANDUSE ─────────────────────────────────────────────────────────────
# Chaque sous-type a un tag explicite : landuse=*, leisure=*, natural=*

def landuse(cfg):
    out = []
    for val, _ in cfg["subtypes"].items():
        s = sc(cfg, val)
        if not s["color"]: continue
        tag = s["tag"] or "landuse"   # défaut : landuse
        l = {"id": f"landuse-{val}", "type": "fill",
             "source": "landuse", "source-layer": "landuse",
             "filter": ["==", ["get", tag], val],
             "paint":  {"fill-color": s["color"]}}
        if s["appear_at"] > 10: l["minzoom"] = s["appear_at"]
        if abs(s["opacity"] - 1.0) > 0.01: l["paint"]["fill-opacity"] = s["opacity"]
        out.append(l)
    return out


# ── Couche GREEN ───────────────────────────────────────────────────────────────
# Filtres mixtes : leisure=park/garden, natural=wood/scrub, landuse=forest/grass…

def green(cfg):
    out = []
    for val, _ in cfg["subtypes"].items():
        s = sc(cfg, val)
        if not s["color"]: continue
        tag = s["tag"] or "landuse"

        # forest + wood : même couleur, sources différentes → regrouper en "any"
        if val == "forest":
            filt = ["any",
                    ["==", ["get", "landuse"], "forest"],
                    ["==", ["get", "natural"], "wood"]]
        elif val == "grass":
            filt = ["any",
                    ["==", ["get", "landuse"], "grass"],
                    ["==", ["get", "landuse"], "meadow"]]
        else:
            filt = ["==", ["get", tag], val]

        # Si wood est défini séparément, forest le couvre déjà via "any"
        if val == "wood" and "forest" in cfg["subtypes"]:
            continue
        # Si meadow est défini séparément, grass le couvre déjà via "any"
        if val == "meadow" and "grass" in cfg["subtypes"]:
            continue

        l = {"id": f"green-{val}", "type": "fill",
             "source": "green", "source-layer": "green",
             "filter": filt,
             "paint":  {"fill-color": s["color"]}}
        if s["appear_at"] > 10: l["minzoom"] = s["appear_at"]
        if abs(s["opacity"] - 1.0) > 0.01: l["paint"]["fill-opacity"] = s["opacity"]
        out.append(l)
    return out


# ── Couche WATER ───────────────────────────────────────────────────────────────

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
    wc = c(wetland.get("color","#d4e2c6"))
    wo = wetland.get("opacity", 0.5)
    out.append({"id":"water-wetland","type":"fill",
        "source":"water","source-layer":"water",
        "filter":["all",["==",["get","natural"],"wetland"],
                        ["==",["geometry-type"],"Polygon"]],
        "paint":{"fill-color":wc,"fill-opacity":wo}})

    for ww,(w,dz) in {"river":([(10,1),(18,12)],10),"canal":([(10,1),(18,10)],10),
                       "stream":([(13,.5),(18,3)],13),"ditch":([(14,.3),(18,2)],14)}.items():
        az = (st.get(ww) or {}).get("appear_at", dz)
        out.append({"id":f"waterway-{ww}","type":"line",
            "source":"water","source-layer":"water","minzoom":az,
            "filter":["all",["==",["get","waterway"],ww],
                            ["!=",["get","tunnel"],"yes"],
                            ["==",["geometry-type"],"LineString"]],
            "paint":{"line-color":col,"line-width":zoom(w)}})
    return out


# ── Couche TREES ───────────────────────────────────────────────────────────────

def trees(cfg):
    col = cfg["color"] or "#6cae50"
    st  = cfg["subtypes"]
    ha  = (st.get("hedge") or {}).get("appear_at", 14)
    ra  = (st.get("tree_row") or {}).get("appear_at", 15)
    ta  = (st.get("tree") or {}).get("appear_at", 17)
    return [
        {"id":"trees-hedge","type":"line",
         "source":"trees","source-layer":"trees","minzoom":ha,
         "filter":["all",["==",["geometry-type"],"LineString"],
                         ["==",["get","barrier"],"hedge"]],
         "layout":{"line-cap":"round","line-join":"round"},
         "paint":{"line-color":"#6ba048","line-width":zoom([(ha,.8),(18,3.5)])}},
        {"id":"trees-row","type":"symbol",
         "source":"trees","source-layer":"trees","minzoom":ra,
         "filter":["all",["==",["geometry-type"],"LineString"],
                         ["==",["get","natural"],"tree_row"]],
         "layout":{"symbol-placement":"line",
                   "symbol-spacing":zoom([(ra,48),(18,32)]),
                   "text-field":"●","text-font":["Noto Sans Regular"],
                   "text-size":zoom([(ra,9),(18,13)]),
                   "text-rotation-alignment":"map"},
         "paint":{"text-color":col,"text-halo-color":"#f2efe9","text-halo-width":.8}},
        {"id":"trees-tree","type":"symbol",
         "source":"trees","source-layer":"trees","minzoom":ta,
         "filter":["all",["==",["geometry-type"],"Point"],
                         ["==",["get","natural"],"tree"]],
         "layout":{"text-field":["match",["get","leaf_type"],"needleleaved","▲","●"],
                   "text-font":["Noto Sans Regular"],
                   "text-size":zoom([(ta,9),(18,13)])},
         "paint":{"text-color":col,"text-halo-color":"#f2efe9","text-halo-width":.9}},
    ]


# ── Couche BUILDINGS ───────────────────────────────────────────────────────────

def buildings(cfg):
    col = cfg["color"] or "#fce1c5"
    bc  = cfg["border_color"] or "#d4a574"
    ap  = cfg["appear_at"]
    out = [{"id":"buildings-fill","type":"fill",
             "source":"buildings","source-layer":"buildings","minzoom":ap,
             "paint":{"fill-color":col}}]
    if cfg["extrusion_3d"]:
        out.append({"id":"buildings-3d","type":"fill-extrusion",
            "source":"buildings","source-layer":"buildings","minzoom":ap,
            "layout":{"visibility":"none"},
            "paint":{"fill-extrusion-color":col,
                     "fill-extrusion-height":["case",
                         ["has","height"],["to-number",["get","height"],6],
                         ["has","building:levels"],["*",["to-number",["get","building:levels"],2],3],
                         7.5],
                     "fill-extrusion-base":0,"fill-extrusion-opacity":.75}})
    out.append({"id":"buildings-outline","type":"line",
        "source":"buildings","source-layer":"buildings","minzoom":ap,
        "paint":{"line-color":bc,"line-width":.5}})
    return out


# ── Couche LEISURE ─────────────────────────────────────────────────────────────

def leisure(cfg):
    st = cfg["subtypes"]
    fc = {k: c((st.get(k) or {}).get("color", cfg["color"])) for k in st}
    fill_expr = ["match",["get","leisure"]]
    for k,col in fc.items():
        if col: fill_expr += [k, col]
    fill_expr.append(cfg["color"] or "#def3c0")
    return [
        {"id":"leisure-fill","type":"fill",
         "source":"leisure","source-layer":"leisure",
         "filter":["==",["geometry-type"],"Polygon"],
         "paint":{"fill-color":fill_expr}},
        {"id":"leisure-outline","type":"line",
         "source":"leisure","source-layer":"leisure",
         "filter":["==",["geometry-type"],"Polygon"],
         "paint":{"line-color":"#adadad","line-width":.5}},
    ]


# ── Couche ROADS ───────────────────────────────────────────────────────────────

def roads(cfg):
    st   = cfg["subtypes"]
    base = cfg["appear_at"]
    out  = []
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
    out.append({"id":"road-labels","type":"symbol",
        "source":"roads","source-layer":"roads","minzoom":cfg["labels_at"],
        "filter":["any"]+[["==",["get","highway"],v]
                          for v in ["primary","secondary","tertiary","residential"]],
        "layout":{"text-field":["get","name"],"text-font":["Noto Sans Regular"],
                  "text-size":11,"symbol-placement":"line","text-max-angle":30},
        "paint":{"text-color":"#333","text-halo-color":"rgba(255,255,255,0.6)",
                 "text-halo-width":1.5}})
    return out


# ── Couche PEDESTRIAN ──────────────────────────────────────────────────────────

def pedestrian(cfg):
    col = cfg["color"] or "#97644c"
    st  = cfg["subtypes"]
    DEFS = {
        "pedestrian_street":("pedestrian",13,[(13,.8),(18,4)],  False),
        "footway":          ("footway",   14,[(14,.5),(18,1.5)],True),
        "path":             ("path",      14,[(14,.5),(18,1.5)],True),
        "steps":            ("steps",     14,[(14,1.5),(18,4)], True),
    }
    out = []
    for key,(hw,dz,wp,dashed) in DEFS.items():
        ap = (st.get(key) or {}).get("appear_at", dz)
        p  = {"line-color":col,"line-width":zoom(wp)}
        if dashed: p["line-dasharray"] = [2,2]
        out.append({"id":f"pedestrian-{key}","type":"line",
            "source":"pedestrian","source-layer":"pedestrian","minzoom":ap,
            "filter":["==",["get","highway"],hw],"paint":p})
    return out


# ── Couche CYCLEWAY ────────────────────────────────────────────────────────────

def cycleway(cfg):
    return [{"id":"cycleway","type":"line",
        "source":"cycleway","source-layer":"cycleway","minzoom":cfg["appear_at"],
        "paint":{"line-color":cfg["color"] or "#0000ff",
                 "line-width":zoom([(cfg["appear_at"],.8),(18,2)]),
                 "line-dasharray":[3,3]}}]


# ── Couche RAILWAY ─────────────────────────────────────────────────────────────

def railway(cfg):
    st  = cfg["subtypes"]
    out = []
    DEFS = {
        "rail":      ([(10,2),(18,7)],[(10,.8),(18,2)],10),
        "subway":    (None,           [(12,.8),(18,2)],12),
        "tram":      (None,           [(13,.5),(18,1.5)],13),
        "miniature": (None,           [(14,.3),(18,1)],14),
    }
    for rw,(ties_w,core_w,dz) in DEFS.items():
        s  = st.get(rw) or {}
        col = c(s.get("color"))
        ap  = s.get("appear_at", dz)
        if not col: continue
        filt = ["all",["==",["get","railway"],rw],
                      ["!=",["get","tunnel"],"yes"],
                      ["!=",["get","bridge"],"yes"]]
        if ties_w:
            out.append({"id":f"railway-{rw}-ties","type":"line",
                "source":"railway","source-layer":"railway","minzoom":ap,"filter":filt,
                "layout":{"line-join":"round"},
                "paint":{"line-color":col,"line-width":zoom(ties_w),"line-dasharray":[.2,4]}})
        out.append({"id":f"railway-{rw}","type":"line",
            "source":"railway","source-layer":"railway","minzoom":ap,"filter":filt,
            "layout":{"line-join":"round"},
            "paint":{"line-color":col,"line-width":zoom(core_w)}})
    return out


# ── Couche PUBLIC TRANSPORT ────────────────────────────────────────────────────

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


# ── Couche BOUNDARIES ──────────────────────────────────────────────────────────

def boundaries(cfg):
    return [{"id":"boundaries","type":"line",
        "source":"boundaries","source-layer":"boundaries","minzoom":cfg["appear_at"],
        "paint":{"line-color":cfg["color"] or "#ac46ac","line-width":1,
                 "line-dasharray":[5,5],"line-opacity":.7}}]


# ── Couche POI ─────────────────────────────────────────────────────────────────

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
             "icon-allow-overlap":True,"icon-padding":2,
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
    layers += water(lc(L,"water"))
    layers += landuse(lc(L,"landuse"))
    layers += green(lc(L,"green"))
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
            LOW  = ["highway","name","ref","tunnel","bridge","layer"]
            HIGH = LOW + ["oneway","maxspeed","lanes","access"]
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
                tag  = scfg.get("tag", "amenity")
                if pap > 10:
                    rules.append({"match":{tag:[pt]},
                                  "zoom_min":10,"zoom_max":pap-1,"action":"drop"})
                rules.append({"match":{tag:[pt]},
                              "zoom_min":pap,"zoom_max":18,"keep_properties":POI_PROPS})
            if ap > 10:
                rules.append({"zoom_min":10,"zoom_max":ap-1,"action":"drop"})
            rules.append({"zoom_min":ap,"zoom_max":18,"keep_properties":POI_PROPS})

        else:
            # Règle générique : utilise le tag explicite du sous-type
            if ap > 10:
                rules.append({"zoom_min":10,"zoom_max":ap-1,"action":"drop"})
            for stk, scfg in st.items():
                scfg = scfg or {}
                sap  = scfg.get("appear_at", ap)
                tag  = scfg.get("tag", name)
                if sap > ap:
                    rules.append({"match":{tag:[stk]},
                                  "zoom_min":ap,"zoom_max":sap-1,"action":"drop"})
            rules.append({"zoom_min":ap,"zoom_max":18,"keep_properties":"ALL"})

        out["layers"][name] = {"rules":rules}
    return out


# ── PMTiles params ─────────────────────────────────────────────────────────────

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

    n = len(config.get("layers",{}))
    print(f"→ {cfg_path}  ({n} couches)")

    only = args.only

    if only in (None,"style"):
        s = build_style(config)
        Path(args.style_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.style_out).write_text(json.dumps(s,indent=2,ensure_ascii=False))
        print(f"✓  {args.style_out}  ({len(s['layers'])} layers MapLibre)")

    if only in (None,"granulometry"):
        g = build_granulometry(config)
        Path(args.gran_out).write_text(json.dumps(g,indent=2,ensure_ascii=False))
        total = sum(len(v["rules"]) for v in g["layers"].values())
        print(f"✓  {args.gran_out}  ({total} règles LOD)")

    if only in (None,"pmtiles"):
        pm = build_pmtiles_params(config)
        Path(args.pmtiles_out).write_text(json.dumps(pm,indent=2,ensure_ascii=False))
        print(f"✓  {args.pmtiles_out}")

    if only is None:
        print("\nSuite :")
        for s in ["bash generate_json.bash",
                  "python3 apply_granulometry.py",
                  "bash generate_pmtiles.bash"]:
            print(f"   {s}")

if __name__ == "__main__":
    main()
