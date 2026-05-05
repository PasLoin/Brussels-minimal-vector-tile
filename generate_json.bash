#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Extraction minimaliste — 6 couches essentielles
# Pré-requis : osmium-tool (apt install osmium-tool)
# ─────────────────────────────────────────────────────────
set -euo pipefail
SRC="brussels_capital_region-latest.osm.pbf"

echo "→ Routes"
osmium tags-filter "$SRC" \
  nwr/highway=motorway,trunk,primary,secondary,tertiary,residential,living_street,unclassified,service \
  -o roads.osm.pbf --overwrite
osmium export roads.osm.pbf -o roads.json --overwrite

echo "→ Bâtiments"
osmium tags-filter "$SRC" \
  nwr/building=yes,house,apartments,commercial,industrial,church,public \
  -o buildings.osm.pbf --overwrite
osmium export buildings.osm.pbf -o buildings.json --overwrite

echo "→ Eau"
osmium tags-filter "$SRC" \
  nwr/natural=water nwr/waterway=river,canal,stream \
  -o water.osm.pbf --overwrite
osmium export water.osm.pbf -o water.json --overwrite

echo "→ Espaces verts"
osmium tags-filter "$SRC" \
  nwr/leisure=park,garden nwr/landuse=forest,meadow,grass nwr/natural=wood \
  -o green.osm.pbf --overwrite
osmium export green.osm.pbf -o green.json --overwrite

echo "→ Occupation du sol"
osmium tags-filter "$SRC" \
  nwr/landuse=residential,industrial,commercial,retail,railway \
  -o landuse.osm.pbf --overwrite
osmium export landuse.osm.pbf -o landuse.json --overwrite

echo "→ Limites administratives"
osmium tags-filter "$SRC" \
  nwr/boundary=administrative \
  -o boundaries.osm.pbf --overwrite
osmium export boundaries.osm.pbf -o boundaries.json --overwrite

echo "✓ 6 couches extraites"
