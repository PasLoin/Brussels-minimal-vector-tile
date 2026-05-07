#!/usr/bin/env python3
"""
extract_stib_routes.py
──────────────────────
osmium export ignore les relations type=route.
Ce script les extrait manuellement en 2 passes :
  1. Trouver les relations STIB/MIVB (tags + member way IDs)
  2. Collecter les géométries des ways membres

Pré-requis : pip install pyosmium
"""
import json
import osmium

SRC = "brussels_capital_region-latest.osm.pbf"
OUT = "public_transport.json"

# ── Pass 1 : scanner les relations ────────────────────────
class RelFinder(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.rels = {}
        self.need_ways = set()

    def relation(self, r):
        tags = dict(r.tags)
        if (tags.get('type') == 'route'
                and tags.get('operator') == 'STIB/MIVB'
                and tags.get('access') != 'no'):
            wids = [m.ref for m in r.members if m.type == 'w']
            self.rels[r.id] = {'tags': tags, 'ways': wids}
            self.need_ways.update(wids)

print("  pass 1 : relations…")
rf = RelFinder()
rf.apply_file(SRC)
print(f"  {len(rf.rels)} relations STIB/MIVB")

if not rf.rels:
    open(OUT, 'w').close()
    print("  0 lignes")
    raise SystemExit(0)

# ── Pass 2 : géométries des ways membres ──────────────────
class WayCollector(osmium.SimpleHandler):
    def __init__(self, needed):
        super().__init__()
        self.needed = needed
        self.geom = {}

    def way(self, w):
        if w.id in self.needed:
            try:
                self.geom[w.id] = [(n.lon, n.lat) for n in w.nodes]
            except osmium.InvalidLocationError:
                pass

print("  pass 2 : géométries…")
wc = WayCollector(rf.need_ways)
wc.apply_file(SRC, locations=True, idx='flex_mem')
print(f"  {len(wc.geom)}/{len(rf.need_ways)} ways résolues")

# ── Construire le GeoJSON (newline-delimited) ─────────────
count = 0
with open(OUT, 'w') as f:
    for rid, rel in rf.rels.items():
        lines = [wc.geom[wid] for wid in rel['ways'] if wid in wc.geom]
        if not lines:
            continue

        geom = ({"type": "LineString", "coordinates": lines[0]}
                if len(lines) == 1
                else {"type": "MultiLineString", "coordinates": lines})

        feature = {"type": "Feature", "geometry": geom, "properties": rel['tags']}
        f.write(json.dumps(feature, ensure_ascii=False) + '\n')
        count += 1

print(f"  {count} features écrites → {OUT}")
