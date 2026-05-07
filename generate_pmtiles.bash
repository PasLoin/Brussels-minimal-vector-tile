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
  [poi]=16
  [pedestrian]=18
  [cycleway]=18
  [railway]=18
  [public_transport]=16
)

REPORT_FILE="sizepmtiles.md"
echo "| Layer | Source Features | Output Features | File Size |" > "$REPORT_FILE"
echo "| :--- | :---: | :---: | :--- |" >> "$REPORT_FILE"

TOTAL_SOURCE=0
TOTAL_OUTPUT=0
TOTAL_SIZE=0

for layer in landuse roads buildings water green boundaries poi pedestrian cycleway railway public_transport; do
  echo "→ ${layer} (z10-${MAX_ZOOM[$layer]})"
  
  # Count source features
  if [ -f "${layer}.json" ]; then
    SRC_COUNT=$(grep -c "^{" "${layer}.json" || wc -l < "${layer}.json")
  else
    SRC_COUNT=0
  fi

  # Run tippecanoe and capture stderr to get feature count
  # Tippecanoe typically outputs "X features, Y bytes of geometry..." to stderr
  TIPPE_LOG=$(tippecanoe -o "${layer}.pmtiles" \
    --name="${layer}" \
    --maximum-zoom="${MAX_ZOOM[$layer]}" \
    "${COMMON_OPTS[@]}" \
    -L "${layer}:${layer}.json" 2>&1 || true)
  
  # Extract output feature count from tippecanoe output
  OUT_COUNT=$(echo "$TIPPE_LOG" | grep -oE '[0-9]+ features' | tail -n 1 | awk '{print $1}' || echo "0")
  [ -z "$OUT_COUNT" ] && OUT_COUNT=0

  if [ -f "${layer}.pmtiles" ]; then
    # In the original script, they just rename to .gz (likely for GitHub Pages auto-compression or just a naming convention)
    mv "${layer}.pmtiles" "${layer}.pmtiles.gz"
  fi
  
  if [ -f "${layer}.pmtiles.gz" ]; then
    FILE_SIZE_BYTES=$(stat -c%s "${layer}.pmtiles.gz" 2>/dev/null || stat -f%z "${layer}.pmtiles.gz")
    FILE_SIZE_HUMAN=$(ls -lh "${layer}.pmtiles.gz" | awk '{print $5}')
  else
    FILE_SIZE_BYTES=0
    FILE_SIZE_HUMAN="0B"
  fi
  
  echo "  ${FILE_SIZE_HUMAN}"
  
  # Add to report
  echo "| ${layer} | ${SRC_COUNT} | ${OUT_COUNT} | ${FILE_SIZE_HUMAN} |" >> "$REPORT_FILE"
  
  TOTAL_SOURCE=$((TOTAL_SOURCE + SRC_COUNT))
  TOTAL_OUTPUT=$((TOTAL_OUTPUT + OUT_COUNT))
  TOTAL_SIZE=$((TOTAL_SIZE + FILE_SIZE_BYTES))
done

# Convert TOTAL_SIZE to human readable
TOTAL_SIZE_HUMAN=$(numfmt --to=iec "$TOTAL_SIZE" 2>/dev/null || echo "$((TOTAL_SIZE / 1024 / 1024))M")

echo "| **Total** | **${TOTAL_SOURCE}** | **${TOTAL_OUTPUT}** | **${TOTAL_SIZE_HUMAN}** |" >> "$REPORT_FILE"

echo ""
echo "✓ Tous les PMTiles générés :"
ls -lh *.pmtiles.gz 2>/dev/null || ls -lh www/*.pmtiles.gz
echo "  Total : ${TOTAL_SIZE_HUMAN}"
echo "✓ Rapport généré : ${REPORT_FILE}"
