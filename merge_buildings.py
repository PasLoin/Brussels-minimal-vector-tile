#!/usr/bin/env python3
"""
Fusionne les bâtiments qui se touchent en un seul polygone.
On garde les trous (cours intérieures, etc.).

Sortie : buildings_merged.json (zoom bas z10-12)
Le fichier buildings_detail.json (zoom haut z13-18) est préservé tel quel.
"""
import json
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from shapely.strtree import STRtree

INPUT = "buildings.json"
OUTPUT = "buildings_merged.json"

print("→ Chargement des bâtiments...")
try:
    with open(INPUT) as f:
        geojson = json.load(f)
except FileNotFoundError:
    print(f"✗ {INPUT} introuvable, skip merge.")
    exit(0)

features = geojson["features"]
print(f"  {len(features)} features en entrée")

# Construire les géométries
geoms = []
skipped_invalid = 0
for feat in features:
    try:
        g = shape(feat["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
        if g.is_empty:
            continue
        if g.is_valid and not g.is_empty:
            geoms.append(g)
    except Exception:
        skipped_invalid += 1
        continue

print(f"  {len(geoms)} géométries valides")
if skipped_invalid:
    print(f"  {skipped_invalid} ignorées (invalides)")

# Index spatial
print("→ Construction de l'index spatial...")
tree = STRtree(geoms)

# Trouver les composantes connexes (bâtiments qui se touchent)
print("→ Recherche des composantes connexes...")
n = len(geoms)
parent = list(range(n))

def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x

def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[ra] = rb

# Pour chaque bâtiment, trouver ceux qui le touchent
for i, geom in enumerate(geoms):
    candidates = tree.query(geom)
    for j in candidates:
        if j != i and find(i) != find(j):
            if geoms[i].intersects(geoms[j]):
                union(i, j)
    if (i + 1) % 50000 == 0:
        print(f"  {i+1}/{n} traités...")

# Regrouper par composante
print("→ Fusion des groupes...")
groups = {}
for i in range(n):
    root = find(i)
    if root not in groups:
        groups[root] = []
    groups[root].append(i)

# Fusionner chaque groupe
merged_features = []
for root, indices in groups.items():
    if len(indices) == 1:
        merged = geoms[indices[0]]
    else:
        merged = unary_union([geoms[i] for i in indices])

    if merged.is_empty:
        continue

    merged_features.append({
        "type": "Feature",
        "properties": {"building": "yes"},
        "geometry": mapping(merged)
    })

print(f"  {len(features)} → {len(merged_features)} features ({100 - len(merged_features)*100//len(features)}% de réduction)")

# Écrire le résultat
out = {
    "type": "FeatureCollection",
    "features": merged_features
}

with open(OUTPUT, "w") as f:
    json.dump(out, f)

print(f"✓ {OUTPUT} écrit")
