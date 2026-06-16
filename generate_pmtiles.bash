#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# PMTiles — un fichier par couche
# Buildings : triple couche (merged z10-12, detail z13-15 grossier, detail z16-18 fin)
# Pré-requis : tippecanoe (github.com/felt/tippecanoe)
# ─────────────────────────────────────────────────────────
set -euo pipefail

COMMON_OPTS=(
  --attribution="© OpenStreetMap contributors"
  --simplify-only-low-zooms
  --drop-densest-as-needed
  --extend-zooms-if-still-dropping
  --generate-ids
  --force
)

# zoom max par couche : détail là où c'est utile
declare -A MAX_ZOOM=(
  [landuse]=18
  [roads]=18
  [water]=18
  [green]=18
  [trees]=18
  [leisure]=18
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
  [water]=2
  [green]=2
  [trees]=2
  [leisure]=2
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

# ── Couches standard (tout sauf buildings) ───────────────
for layer in landuse roads water green trees leisure boundaries poi pedestrian cycleway railway public_transport; do
  echo "→ ${layer} (z10-${MAX_ZOOM[$layer]})"
  
  if [ -f "${layer}.json" ]; then
    SRC_COUNT=$(grep -c "^{" "${layer}.json" || wc -l < "${layer}.json")
  else
    SRC_COUNT=0
  fi

  TIPPE_LOG=$(tippecanoe -o "${layer}.pmtiles" \
    --name="${layer}" \
    --minimum-zoom=10 \
    --maximum-zoom="${MAX_ZOOM[$layer]}" \
    --simplification="${SIMPLIFICATION[$layer]:-30}" \
    "${COMMON_OPTS[@]}" \
    -L "${layer}:${layer}.json" 2>&1 || true)

  echo "$TIPPE_LOG"
  
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
  
  echo "| ${layer} | ${SRC_COUNT} | ${OUT_COUNT} | ${FILE_SIZE_HUMAN} |" >> "$REPORT_FILE"
  
  TOTAL_SOURCE=$((TOTAL_SOURCE + SRC_COUNT))
  TOTAL_OUTPUT=$((TOTAL_OUTPUT + OUT_COUNT))
  TOTAL_SIZE=$((TOTAL_SIZE + FILE_SIZE_BYTES))
done

# ── Buildings : triple couche dans un seul PMTiles ───────
# Pourquoi 3 paliers et pas 2 : à simplification=2 uniforme sur tout
# z13-18, l'archive complète pèse ~80 Mo — trop proche de la limite
# dure GitHub de 100 Mo sans marge pour la croissance future des
# données OSM. z13-15 (vue d'ensemble, zoom modéré) n'a pas besoin de
# la même finesse géométrique que z16-18 (zoom rapproché, où chaque
# détail de contour compte visuellement) -> simplification=4 sur le
# premier sous-palier, simplification=2 conservé sur le second.
echo "→ buildings (merged z10-12 + detail z13-15 + detail z16-18)"

SRC_MERGED=0
SRC_DETAIL=0
if [ -f "buildings_merged.json" ]; then
  SRC_MERGED=$(grep -c "^{" "buildings_merged.json" || wc -l < "buildings_merged.json")
fi
if [ -f "buildings_detail.json" ]; then
  SRC_DETAIL=$(grep -c "^{" "buildings_detail.json" || wc -l < "buildings_detail.json")
fi
SRC_COUNT=$((SRC_MERGED + SRC_DETAIL))

# IMPORTANT : --minimum-zoom=10 --maximum-zoom=18 forcés explicitement
# en options globales (cf. issue précédente : sans ça, l'heuristique
# de densité de tippecanoe peut réduire silencieusement le maxzoom
# effectif de toute l'archive en dessous de 18, vidant les hauts
# niveaux de zoom).
TIPPE_LOG=$(tippecanoe -o buildings.pmtiles \
  --attribution="© OpenStreetMap contributors" \
  --minimum-zoom=10 \
  --maximum-zoom=18 \
  --simplify-only-low-zooms \
  --drop-densest-as-needed \
  --generate-ids \
  --force \
  -L'{"file":"buildings_merged.json","layer":"buildings","minimum-zoom":10,"maximum-zoom":12,"simplification":2}' \
  -L'{"file":"buildings_detail.json","layer":"buildings","minimum-zoom":13,"maximum-zoom":15,"simplification":4}' \
  -L'{"file":"buildings_detail.json","layer":"buildings","minimum-zoom":16,"maximum-zoom":18,"simplification":2}' \
  2>&1 || true)

echo "$TIPPE_LOG"

OUT_COUNT=$(echo "$TIPPE_LOG" | grep -oE '[0-9]+ features' | tail -n 1 | awk '{print $1}' || echo "0")
[ -z "$OUT_COUNT" ] && OUT_COUNT=0

if [ -f "buildings.pmtiles" ]; then
  mv "buildings.pmtiles" "buildings.pmtiles.gz"
fi

if [ -f "buildings.pmtiles.gz" ]; then
  FILE_SIZE_BYTES=$(stat -c%s "buildings.pmtiles.gz" 2>/dev/null || stat -f%z "buildings.pmtiles.gz")
  FILE_SIZE_HUMAN=$(ls -lh "buildings.pmtiles.gz" | awk '{print $5}')
else
  FILE_SIZE_BYTES=0
  FILE_SIZE_HUMAN="0B"
fi

echo "  ${FILE_SIZE_HUMAN}"

echo "| buildings (merged z10-12) | ${SRC_MERGED} | - | - |" >> "$REPORT_FILE"
echo "| buildings (detail z13-15, simpl.4) | ${SRC_DETAIL} | - | - |" >> "$REPORT_FILE"
echo "| buildings (detail z16-18, simpl.2) | ${SRC_DETAIL} | - | - |" >> "$REPORT_FILE"
echo "| **buildings total** | **${SRC_COUNT}** | **${OUT_COUNT}** | **${FILE_SIZE_HUMAN}** |" >> "$REPORT_FILE"

TOTAL_SOURCE=$((TOTAL_SOURCE + SRC_COUNT))
TOTAL_OUTPUT=$((TOTAL_OUTPUT + OUT_COUNT))
TOTAL_SIZE=$((TOTAL_SIZE + FILE_SIZE_BYTES))

# ── Building parts : fichier séparé, mode 3D uniquement ──
# issue #40 — z13-18 seulement (pas de couche basse résolution z10-12,
# ces détails ne servent qu'au mode 3D, jamais chargés en 2D). Pas dans
# la boucle standard ci-dessus car celle-ci force minimum-zoom=10 pour
# toutes les couches, ce qui serait inutile ici.
echo "→ building_parts (z13-18)"

SRC_COUNT=0
if [ -f "building_parts.json" ]; then
  SRC_COUNT=$(grep -c "^{" "building_parts.json" || wc -l < "building_parts.json")
fi

TIPPE_LOG=$(tippecanoe -o building_parts.pmtiles \
  --name="building_parts" \
  --minimum-zoom=13 \
  --maximum-zoom=18 \
  --simplification=2 \
  "${COMMON_OPTS[@]}" \
  -L "building_parts:building_parts.json" 2>&1 || true)

echo "$TIPPE_LOG"

OUT_COUNT=$(echo "$TIPPE_LOG" | grep -oE '[0-9]+ features' | tail -n 1 | awk '{print $1}' || echo "0")
[ -z "$OUT_COUNT" ] && OUT_COUNT=0

if [ -f "building_parts.pmtiles" ]; then
  mv "building_parts.pmtiles" "building_parts.pmtiles.gz"
fi

if [ -f "building_parts.pmtiles.gz" ]; then
  FILE_SIZE_BYTES=$(stat -c%s "building_parts.pmtiles.gz" 2>/dev/null || stat -f%z "building_parts.pmtiles.gz")
  FILE_SIZE_HUMAN=$(ls -lh "building_parts.pmtiles.gz" | awk '{print $5}')
else
  FILE_SIZE_BYTES=0
  FILE_SIZE_HUMAN="0B"
fi

echo "  ${FILE_SIZE_HUMAN}"

echo "| building_parts | ${SRC_COUNT} | ${OUT_COUNT} | ${FILE_SIZE_HUMAN} |" >> "$REPORT_FILE"

TOTAL_SOURCE=$((TOTAL_SOURCE + SRC_COUNT))
TOTAL_OUTPUT=$((TOTAL_OUTPUT + OUT_COUNT))
TOTAL_SIZE=$((TOTAL_SIZE + FILE_SIZE_BYTES))

# ── Total ────────────────────────────────────────────────
TOTAL_SIZE_HUMAN=$(numfmt --to=iec "$TOTAL_SIZE" 2>/dev/null || echo "$((TOTAL_SIZE / 1024 / 1024))M")

echo "| **Total** | **${TOTAL_SOURCE}** | **${TOTAL_OUTPUT}** | **${TOTAL_SIZE_HUMAN}** |" >> "$REPORT_FILE"

echo ""
echo "✓ Tous les PMTiles générés :"
ls -lh *.pmtiles.gz 2>/dev/null || ls -lh www/*.pmtiles.gz
echo "  Total : ${TOTAL_SIZE_HUMAN}"
echo "✓ Rapport généré : ${REPORT_FILE}"
