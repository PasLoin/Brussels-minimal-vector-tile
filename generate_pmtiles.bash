#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# PMTiles — un fichier par couche
# Pré-requis : tippecanoe (github.com/felt/tippecanoe)
# ─────────────────────────────────────────────────────────
set -euo pipefail

COMMON_OPTS=(
  --attribution="© OpenStreetMap contributors"
  --minimum-zoom=10
  --simplify-only-low-zooms
  --drop-densest-as-needed
  --extend-zooms-if-still-dropping
  --coalesce-densest-as-needed
  --generate-ids
  --force
)

# zoom max par couche : détail là où c'est utile
declare -A MAX_ZOOM=(
  [landuse]=18
  [roads]=18
  [buildings]=18
  [water]=18
  [green]=18
  [trees]=18
  [boundaries]=14
  [poi]=16
  [pedestrian]=18
  [cycleway]=18
  [railway]=18
  [public_transport]=16
)

# simplification par couche
declare -A SIMPLIFICATION=(
  [landuse]=2
  [roads]=2
  [buildings]=2
  [water]=2
  [green]=2
  [trees]=2
  [boundaries]=10
  [poi]=10
  [pedestrian]=10
  [cycleway]=10
  [railway]=10
  [public_transport]=10
)

REPORT_FILE="sizepmtiles.md"
echo "| Layer | Source Features | Output Features | File Size |" > "$REPORT_FILE"
echo "| :--- | :---: | :---: | :--- |" >> "$REPORT_FILE"

TOTAL_SOURCE=0
TOTAL_OUTPUT=0
TOTAL_SIZE=0

for layer in landuse roads buildings water green trees boundaries poi pedestrian cycleway railway public_transport; do
  echo "→ ${layer} (z10-${MAX_ZOOM[$layer]})"
  
  # Count source features
  if [ -f "${layer}.json" ]; then
    SRC_COUNT=$(grep -c "^{" "${layer}.json" || wc -l < "${layer}.json")
  else
    SRC_COUNT=0
  fi

  # Run tippecanoe and capture stderr to get feature count
  TIPPE_LOG=$(tippecanoe -o "${layer}.pmtiles" \
    --name="${layer}" \
    --maximum-zoom="${MAX_ZOOM[$layer]}" \
    --simplification="${SIMPLIFICATION[$layer]:-30}" \
    "${COMMON_OPTS[@]}" \
    -L "${layer}:${layer}.json" 2>&1 || true)

  echo "$TIPPE_LOG"
  
  # Extract output feature count from tippecanoe output
  OUT_COUNT=$(echo "$TIPPE_LOG" | grep -oE '[0-9]+ features' | tail -n 1 | awk '{print $1}' || echo "0")
  [ -z "$OUT_COUNT" ] && OUT_COUNT=0

  if [ -f "${layer}.pmtiles" ]; then
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
