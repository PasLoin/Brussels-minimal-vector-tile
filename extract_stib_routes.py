#!/usr/bin/env python3
"""
extract_stib_routes.py
──────────────────────
Construit le GeoJSON des routes STIB/MIVB à partir d'un export OSM XML.
Aucune dépendance externe (xml.etree.ElementTree = stdlib).

Entrée : _tmp_pt.osm  (généré par osmium cat)
Sortie : public_transport.json  (GeoJSON newline-delimited)
"""
import json
import xml.etree.ElementTree as ET

OSM_FILE = "_tmp_pt.osm"
OUT = "public_transport.json"

nodes = {}   # id → (lon, lat)
ways = {}    # id → [(lon, lat), …]
rels = []    # [{tags, way_ids}]

# ── Parse XML incrémental (économe en mémoire) ───────────
for _, elem in ET.iterparse(OSM_FILE, events=("end",)):

    if elem.tag == "node":
        nid = int(elem.get("id"))
        lon = elem.get("lon")
        lat = elem.get("lat")
        if lon and lat:
            nodes[nid] = (float(lon), float(lat))
        elem.clear()

    elif elem.tag == "way":
        wid = int(elem.get("id"))
        ways[wid] = [int(nd.get("ref")) for nd in elem.findall("nd")]
        elem.clear()

    elif elem.tag == "relation":
        tags = {t.get("k"): t.get("v") for t in elem.findall("tag")}
        if (tags.get("type") == "route"
                and tags.get("operator") == "STIB/MIVB"
                and tags.get("access") != "no"):
            wids = [int(m.get("ref"))
                    for m in elem.findall("member")
                    if m.get("type") == "way"]
            rels.append({"tags": tags, "ways": wids})
        elem.clear()

print(f"  {len(rels)} relations, {len(ways)} ways, {len(nodes)} noeuds")

# ── Construire le GeoJSON ─────────────────────────────────
count = 0
with open(OUT, "w") as f:
    for rel in rels:
        lines = []
        for wid in rel["ways"]:
            if wid not in ways:
                continue
            coords = [nodes[nid] for nid in ways[wid] if nid in nodes]
            if len(coords) >= 2:
                lines.append(coords)

        if not lines:
            continue

        geom = ({"type": "LineString", "coordinates": lines[0]}
                if len(lines) == 1
                else {"type": "MultiLineString", "coordinates": lines})

        feature = {
            "type": "Feature",
            "geometry": geom,
            "properties": rel["tags"],
        }
        f.write(json.dumps(feature, ensure_ascii=False) + "\n")
        count += 1

print(f"  {count} features -> {OUT}")
