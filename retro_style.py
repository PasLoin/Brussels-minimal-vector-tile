#!/usr/bin/env python3
"""
retro_style.py  —  style.json MapLibre → map.config.yaml
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

# Pour chaque groupe, quels tags OSM chercher dans les filtres
# et quel tag associer à chaque valeur trouvée
GROUP_TAGS = {
    "landuse":  ["landuse"],
    "water":    ["waterway","natural"],
    "green":    ["leisure","natural","landuse"],   # ordre priorité
    "trees":    ["natural","barrier"],
    "buildings":["building"],
    "leisure":  ["leisure"],
    "roads":    ["highway"],
    "pedestrian":["highway"],
    "railway":  ["railway"],
    "poi":      ["amenity","shop","tourism"],
    "boundaries":["boundary"],
}

def first_color(paint):
    for k in ("fill-color","line-color","circle-color","text-color","fill-extrusion-color"):
        v = paint.get(k)
        if not v: continue
        if isinstance(v,str) and v.startswith("#"): return v
        if isinstance(v,list):
            if v[0] in ("match","case") and len(v)>=2:
                last=v[-1]
                if isinstance(last,str) and last.startswith("#"): return last
            if v[0]=="interpolate" and len(v)>4:
                last=v[-1]
                if isinstance(last,str) and last.startswith("#"): return last
    return None

def min_zoom_of(layer):
    z = layer.get("minzoom",10)
    for block in (layer.get("paint",{}),layer.get("layout",{})):
        for v in block.values():
            if isinstance(v,list) and len(v)>3 and v[0]=="interpolate":
                try: z=max(z,int(v[3]))
                except: pass
    return max(int(z),10)

def filter_values(filt, tag):
    if not isinstance(filt,list) or not filt: return []
    op=filt[0]
    if op=="==" and len(filt)==3:
        lhs,rhs=filt[1],filt[2]
        if lhs==["get",tag] or lhs==tag:
            return [str(rhs)] if isinstance(rhs,(str,int)) else []
    if op in ("in","match") and len(filt)>=3:
        lhs=filt[1]
        if lhs==["get",tag] or lhs==tag:
            vals=filt[2]
            if isinstance(vals,list) and vals[0]=="literal":
                return [str(v) for v in vals[1]]
            return [str(v) for v in filt[2:] if isinstance(v,str)]
    if op in ("any","all"):
        out=[]
        for sub in filt[1:]: out+=filter_values(sub,tag)
        return out
    return []

def analyse_group(name, style_layers):
    prefixes = GROUPS[name]
    matched  = [l for l in style_layers
                if any(l["id"].startswith(p) for p in prefixes) and l.get("source")]
    if not matched: return None

    zmins    = [min_zoom_of(l) for l in matched]
    appear   = min(zmins) if zmins else 10

    main_color = None
    for l in matched:
        col = first_color(l.get("paint",{}))
        if col: main_color=col; break

    visible = not any(
        l.get("layout",{}).get("visibility")=="none"
        for l in matched
        if not l["id"].endswith("-3d")
    )

    # Sous-types : on cherche les valeurs de tag + leur tag associé
    tags_to_check = GROUP_TAGS.get(name, ["type"])
    subtypes = {}   # val → {tag, color, appear_at}

    for l in matched:
        filt = l.get("filter")
        if not filt: continue
        lz   = min_zoom_of(l)
        lc   = first_color(l.get("paint",{}))

        for tag in tags_to_check:
            vals = filter_values(filt, tag)
            for v in vals:
                if v not in subtypes:
                    subtypes[v] = {"tag": tag}
                # Couleur spécifique différente de la couleur principale
                if lc and lc != main_color:
                    subtypes[v]["color"] = lc
                # appear_at spécifique
                if lz > appear:
                    subtypes[v]["appear_at"] = lz

    # Nettoyer les sous-types qui n'apportent rien (ni couleur ni zoom différent)
    cleaned = {}
    for k, v in subtypes.items():
        entry = {"tag": v["tag"]}
        if "color" in v:    entry["color"]     = v["color"]
        if "appear_at" in v: entry["appear_at"] = v["appear_at"]
        cleaned[k] = entry

    return {"appear_at":appear,"main_color":main_color,
            "visible":visible,"subtypes":cleaned}

def dump_layer(name, info):
    lines = []
    label  = LABELS.get(name, name.capitalize())
    appear = info["appear_at"]
    col    = info["main_color"]
    vis    = info["visible"]

    lines.append(f"  {name}:")
    lines.append(f"    label: {label}")
    if col:
        lines.append(f"    color: \"{col}\"")
    if not vis:
        lines.append(f"    visible: false")
    lines.append(f"    appear_at: {appear}")

    if info["subtypes"]:
        lines.append(f"    subtypes:")
        for val, scfg in sorted(info["subtypes"].items()):
            parts = [f"tag: {scfg['tag']}"]
            if "color" in scfg:     parts.append(f"color: \"{scfg['color']}\"")
            if "appear_at" in scfg: parts.append(f"appear_at: {scfg['appear_at']}")
            lines.append(f"      {val}: {{ {', '.join(parts)} }}")

    return "\n".join(lines)

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
                   for l in style_layers if l.get("type")=="background"),"#f2efe9")
    glyphs = style.get("glyphs",
        "https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf")

    groups = {}
    for name in GROUPS:
        info = analyse_group(name, style_layers)
        if not info: continue
        groups[name] = info
        st_n = len(info["subtypes"])
        print(f"   {name:22s} appear_at={info['appear_at']:2d}  "
              f"color={info['main_color'] or '—':9s}  {st_n} sous-types")

    out_lines = [
        "# ─────────────────────────────────────────────────────────────────────",
        f"# map.config.yaml  —  généré depuis {style_path}  par retro_style.py",
        "#",
        "# Modifier CE fichier, pas style.json directement.",
        "# Regénérer :  python3 build_map.py",
        "# ─────────────────────────────────────────────────────────────────────",
        "",
        "map:",
        "  name: Map",
        "  center: [4.3517, 50.8503]",
        "  zoom: 13",
        f"  background: \"{bg}\"",
        "  font: \"#734a08\"",
        f"  glyphs: \"{glyphs}\"",
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
