#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# PMTiles — un fichier par couche
# Pré-requis : tippecanoe (github.com/felt/tippecanoe)
# ─────────────────────────────────────────────────────────
set -euo pipefail

COMMON_OPTS=(
  --attribution="© OpenStreetMap contributors"
  --minimum-zoom=10
  --simplification=30
  --simplify-only-low-zooms
  --drop-densest-as-needed
  --extend-zooms-if-still-dropping
  --coalesce-densest-as-needed
  --generate-ids
  --force
)

# zoom max par couche : détail là où c'est utile
declare -A MAX_ZOOM=(
  [landuse]=14
  [roads]=18
  [buildings]=18
  [water]=16
  [green]=16
  [boundaries]=14
)

for layer in landuse roads buildings water green boundaries; do
  echo "→ ${layer} (z10-${MAX_ZOOM[$layer]})"
  tippecanoe -o "${layer}.pmtiles" \
    --name="${layer}" \
    --maximum-zoom="${MAX_ZOOM[$layer]}" \
    "${COMMON_OPTS[@]}" \
    -L "${layer}:${layer}.json"
  mv "${layer}.pmtiles" "${layer}.pmtiles.gz"
  echo "  $(ls -lh "${layer}.pmtiles.gz" | awk '{print $5}')"
done

echo ""
echo "✓ Tous les PMTiles générés :"
ls -lh *.pmtiles.gz
echo "  Total : $(du -ch *.pmtiles.gz | tail -1 | awk '{print $1}')"
