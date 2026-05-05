#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# PMTiles — poids minimal
# Pré-requis : tippecanoe (github.com/felt/tippecanoe)
# ─────────────────────────────────────────────────────────
set -euo pipefail

tippecanoe -o brussels.pmtiles --force \
  --name="Brussels Minimal" \
  --attribution="© OpenStreetMap contributors" \
  --minimum-zoom=10 \
  --maximum-zoom=18 \
  --simplification=20 \
  --drop-densest-as-needed \
  --extend-zooms-if-still-dropping \
  --no-tile-size-limit \
  --coalesce-densest-as-needed \
  --generate-ids \
  -L landuse:landuse.json \
  -L roads:roads.json \
  -L buildings:buildings.json \
  -L water:water.json \
  -L green:green.json \
  -L boundaries:boundaries.json

echo "✓ brussels.pmtiles généré"
mv brussels.pmtiles brussels.pmtiles.gz
ls -lh brussels.pmtiles.gz
