#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Extraction minimaliste — 6 couches essentielles
# Pré-requis : osmium-tool
# ─────────────────────────────────────────────────────────
set -euo pipefail

SRC="brussels_capital_region-latest.osm.pbf"

# Vérifier que le fichier source existe et est un PBF valide
if [ ! -f "$SRC" ]; then
  echo "✗ Fichier $SRC introuvable" >&2; exit 1
fi

FILESIZE=$(stat -c%s "$SRC" 2>/dev/null || stat -f%z "$SRC")
if [ "$FILESIZE" -lt 1000000 ]; then
  echo "✗ $SRC trop petit (${FILESIZE} octets) — téléchargement probablement échoué" >&2; exit 1
fi

# Vérifier que c'est bien un PBF et pas une page HTML
FILETYPE=$(file -b "$SRC")
if [[ "$FILETYPE" != *"OpenStreetMap"* ]]; then
  echo "✗ $SRC n'est pas un fichier PBF valide" >&2
  echo "  Détecté : $FILETYPE" >&2
  exit 1
fi

echo "✓ Source valide : $SRC ($(numfmt --to=iec "$FILESIZE"))"

extract() {
  local name="$1"; shift
  echo "→ $name"
  osmium tags-filter "$SRC" "$@" -o "_tmp_${name}.osm.pbf" --overwrite
  osmium export "_tmp_${name}.osm.pbf" -o "${name}.json" --overwrite
  rm -f "_tmp_${name}.osm.pbf"
  echo "  $(wc -l < "${name}.json") lignes"
}

extract roads \
  nwr/highway=motorway,trunk,primary,secondary,tertiary,residential,living_street,unclassified,service

# Buildings : extraction spéciale pour les multipolygones
echo "→ buildings"
# 1. Ways simples avec building=*
osmium tags-filter "$SRC" w/building=* -o _tmp_bldg_ways.osm.pbf --overwrite

# 2. Relations multipolygones avec building=*
osmium tags-filter "$SRC" r/building=* -o _tmp_bldg_rels.osm.pbf --overwrite

# 3. Extraire les IDs des relations pour récupérer leurs membres
osmium cat _tmp_bldg_rels.osm.pbf -f opl 2>/dev/null | awk '/^r/{print $1}' > _tmp_rel_ids.txt || true

if [ -s _tmp_rel_ids.txt ]; then
  REL_COUNT=$(wc -l < _tmp_rel_ids.txt)
  echo "  ${REL_COUNT} relations multipolygones trouvées"
  # 4. Récupérer les relations + leurs ways membres depuis le fichier source
  osmium getid -r "$SRC" -i _tmp_rel_ids.txt -o _tmp_bldg_rels_complete.osm.pbf --overwrite
  # 5. Fusionner ways simples + relations complètes
  osmium merge _tmp_bldg_ways.osm.pbf _tmp_bldg_rels_complete.osm.pbf -o _tmp_buildings.osm.pbf --overwrite
else
  echo "  0 relations multipolygones"
  cp _tmp_bldg_ways.osm.pbf _tmp_buildings.osm.pbf
fi

osmium export _tmp_buildings.osm.pbf -o buildings.json --overwrite
rm -f _tmp_bldg_*.osm.pbf _tmp_rel_ids.txt
echo "  $(wc -l < buildings.json) lignes"

extract water \
  nwr/natural=water nwr/waterway=river,canal,stream,ditch nwr/landuse=basin nwr/natural=wetland

extract green \
  nwr/leisure=park,garden nwr/landuse=forest,meadow,grass nwr/natural=wood

extract landuse \
  nwr/landuse=residential,industrial,commercial,retail,railway

extract boundaries \
  nwr/boundary=administrative

echo "✓ 6 couches extraites"
