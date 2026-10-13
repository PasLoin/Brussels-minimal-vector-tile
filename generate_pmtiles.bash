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
  python3 - "$@" << 'COUNT'
import json, sys
total = 0
for path in sys.argv[1:]:
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        continue
    if not text.strip():
        continue
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        total += sum(1 for line in text.splitlines() if line.lstrip().startswith("{"))
        continue
    if isinstance(data, dict) and data.get("type") == "FeatureCollection":
        total += len(data.get("features") or [])
    elif isinstance(data, dict) and data.get("type") == "Feature":
        total += 1
print(total)
COUNT
}

warn() {
  if [ -n "${GITHUB_ACTIONS:-}" ]; then
    echo "::warning::$1"
  else
    echo "  ⚠  $1" >&2
  fi
}

REPORT_FILE="sizepmtiles.md"
echo "| Layer | Source Features | Tippecanoe Features | File Size |" > "$REPORT_FILE"
echo "| :--- | :---: | :---: | :--- |" >> "$REPORT_FILE"

TOTAL_SOURCE=0
TOTAL_OUTPUT=0
TOTAL_SIZE=0
SKIPPED_LAYERS=()

mapfile -t LAYERS < <(param layers)
for layer in "${LAYERS[@]}"; do
  read -r MINZ MAXZ SIMPL < <(param settings "$layer")
  rm -f "${layer}.pmtiles" "${layer}.pmtiles.gz"

  INPUT_ARGS=()
  INPUT_FILES=()
  while IFS=$'\t' read -r file zmin zmax; do
    [ -z "$file" ] && continue
    if [ ! -f "$file" ]; then
      warn "${layer} : ${file} absent"
      continue
    fi
    INPUT_FILES+=("$file")
    INPUT_ARGS+=(-L "{\"file\":\"${file}\",\"layer\":\"${layer}\"}")
    echo "→ ${layer} ← ${file} (z${zmin}-${zmax})"
  done < <(param inputs "$layer")

  if [ "${#INPUT_ARGS[@]}" -eq 0 ]; then
    warn "${layer} : aucune source, couche ignorée (la version précédente reste dans www/)"
    echo "| ${layer} (z${MINZ}-${MAXZ}) | — | — | absente (ignorée) |" >> "$REPORT_FILE"
    SKIPPED_LAYERS+=("$layer")
    continue
  fi

  SRC_COUNT=$(count_features "${INPUT_FILES[@]}")

  if [ "$SRC_COUNT" -eq 0 ]; then
    warn "${layer} : 0 feature en entrée, couche ignorée (la version précédente reste dans www/)"
    echo "| ${layer} (z${MINZ}-${MAXZ}) | 0 | — | vide (ignorée) |" >> "$REPORT_FILE"
    SKIPPED_LAYERS+=("$layer")
    continue
  fi

  if ! TIPPE_LOG=$(tippecanoe -o "${layer}.pmtiles" \
      --name="${layer}" \
      --minimum-zoom="${MINZ}" \
      --maximum-zoom="${MAXZ}" \
      --simplification="${SIMPL}" \
      "${COMMON_OPTS[@]}" \
      "${INPUT_ARGS[@]}" 2>&1); then
    echo "$TIPPE_LOG" >&2
    echo "✗ tippecanoe a échoué pour la couche ${layer}" >&2
    exit 1
  fi
  echo "$TIPPE_LOG"

  if [ ! -s "${layer}.pmtiles" ]; then
    echo "✗ tippecanoe n'a produit aucun fichier pour la couche ${layer}" >&2
    exit 1
  fi
  mv "${layer}.pmtiles" "${layer}.pmtiles.gz"

  OUT_COUNT=$(printf '%s\n' "$TIPPE_LOG" | grep -oE '[0-9]+ features' | tail -n 1 | awk '{print $1}' || true)
  [ -z "$OUT_COUNT" ] && OUT_COUNT=0

  FILE_SIZE_BYTES=$(stat -c%s "${layer}.pmtiles.gz" 2>/dev/null || stat -f%z "${layer}.pmtiles.gz")
  FILE_SIZE_HUMAN=$(ls -lh "${layer}.pmtiles.gz" | awk '{print $5}')

  echo "  ${FILE_SIZE_HUMAN}"
  echo "| ${layer} (z${MINZ}-${MAXZ}) | ${SRC_COUNT} | ${OUT_COUNT} | ${FILE_SIZE_HUMAN} |" >> "$REPORT_FILE"

  TOTAL_SOURCE=$((TOTAL_SOURCE + SRC_COUNT))
  TOTAL_OUTPUT=$((TOTAL_OUTPUT + OUT_COUNT))
  TOTAL_SIZE=$((TOTAL_SIZE + FILE_SIZE_BYTES))
done

TOTAL_SIZE_HUMAN=$(numfmt --to=iec "$TOTAL_SIZE" 2>/dev/null || echo "$((TOTAL_SIZE / 1024 / 1024))M")
echo "| **Total** | **${TOTAL_SOURCE}** | **${TOTAL_OUTPUT}** | **${TOTAL_SIZE_HUMAN}** |" >> "$REPORT_FILE"

echo ""
echo "✓ PMTiles générés :"
ls -lh ./*.pmtiles.gz 2>/dev/null || echo "  (aucun)"
echo "  Total : ${TOTAL_SIZE_HUMAN}"
if [ "${#SKIPPED_LAYERS[@]}" -gt 0 ]; then
  warn "couches ignorées : ${SKIPPED_LAYERS[*]}"
fi
echo "✓ Rapport généré : ${REPORT_FILE}"
