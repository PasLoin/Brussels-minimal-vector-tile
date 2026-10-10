#!/bin/bash
set -euo pipefail

PARAMS="${PMTILES_PARAMS:-pmtiles_params.json}"
if [ ! -f "$PARAMS" ]; then
  python3 build_map.py --only pmtiles --pmtiles-out "$PARAMS"
fi

COMMON_OPTS=(
  --attribution="© OpenStreetMap contributors"
  --simplify-only-low-zooms
  --drop-densest-as-needed
  --extend-zooms-if-still-dropping
  --generate-ids
  --force
)

param() {
  python3 - "$PARAMS" "$@" << 'PARAM'
import json, sys
params = json.load(open(sys.argv[1]))["layers"]
what = sys.argv[2]
if what == "layers":
    print("\n".join(params))
elif what == "settings":
    p = params[sys.argv[3]]
    print(p["min_zoom"], p["max_zoom"], p["simplification"])
elif what == "inputs":
    layer = sys.argv[3]
    for i in params[layer]["inputs"]:
        print(f"{i['file']}\t{i['min_zoom']}\t{i['max_zoom']}")
PARAM
}

count_features() {
  local total=0 n
  for f in "$@"; do
    if [ -f "$f" ]; then
      n=$(grep -c "^{" "$f" || wc -l < "$f")
      total=$((total + n))
    fi
  done
  echo "$total"
}

REPORT_FILE="sizepmtiles.md"
echo "| Layer | Source Features | Output Features | File Size |" > "$REPORT_FILE"
echo "| :--- | :---: | :---: | :--- |" >> "$REPORT_FILE"

TOTAL_SOURCE=0
TOTAL_OUTPUT=0
TOTAL_SIZE=0

mapfile -t LAYERS < <(param layers)
for layer in "${LAYERS[@]}"; do
  read -r MINZ MAXZ SIMPL < <(param settings "$layer")
  INPUT_ARGS=()
  INPUT_FILES=()
  while IFS=$'\t' read -r file zmin zmax; do
    [ -z "$file" ] && continue
    if [ ! -f "$file" ]; then
      echo "  ⚠  ${file} absent"
      continue
    fi
    INPUT_FILES+=("$file")
    INPUT_ARGS+=(-L "{\"file\":\"${file}\",\"layer\":\"${layer}\"}")
    echo "→ ${layer} ← ${file} (z${zmin}-${zmax})"
  done < <(param inputs "$layer")

  if [ "${#INPUT_ARGS[@]}" -eq 0 ]; then
    echo "  ⚠  ${layer} : aucune source, couche ignorée"
    continue
  fi

  SRC_COUNT=$(count_features "${INPUT_FILES[@]}")

  TIPPE_LOG=$(tippecanoe -o "${layer}.pmtiles" \
    --name="${layer}" \
    --minimum-zoom="${MINZ}" \
    --maximum-zoom="${MAXZ}" \
    --simplification="${SIMPL}" \
    "${COMMON_OPTS[@]}" \
    "${INPUT_ARGS[@]}" 2>&1 || true)
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
  echo "| ${layer} (z${MINZ}-${MAXZ}) | ${SRC_COUNT} | ${OUT_COUNT} | ${FILE_SIZE_HUMAN} |" >> "$REPORT_FILE"

  TOTAL_SOURCE=$((TOTAL_SOURCE + SRC_COUNT))
  TOTAL_OUTPUT=$((TOTAL_OUTPUT + OUT_COUNT))
  TOTAL_SIZE=$((TOTAL_SIZE + FILE_SIZE_BYTES))
done

TOTAL_SIZE_HUMAN=$(numfmt --to=iec "$TOTAL_SIZE" 2>/dev/null || echo "$((TOTAL_SIZE / 1024 / 1024))M")
echo "| **Total** | **${TOTAL_SOURCE}** | **${TOTAL_OUTPUT}** | **${TOTAL_SIZE_HUMAN}** |" >> "$REPORT_FILE"

echo ""
echo "✓ Tous les PMTiles générés :"
ls -lh *.pmtiles.gz 2>/dev/null || ls -lh www/*.pmtiles.gz
echo "  Total : ${TOTAL_SIZE_HUMAN}"
echo "✓ Rapport généré : ${REPORT_FILE}"
