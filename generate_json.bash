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

# Vérifier les magic bytes du format PBF (commence par 0x0000000d)
MAGIC=$(xxd -l 4 -p "$SRC")
if [ "$MAGIC" != "0000000d" ]; then
  echo "✗ $SRC n'est pas un fichier PBF valide (magic: $MAGIC)" >&2
  echo "  Le téléchargement a peut-être renvoyé une page HTML." >&2
  head -c 200 "$SRC" >&2
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

extract buildings \
  nwr/building=yes,house,apartments,commercial,industrial,church,public

extract water \
  nwr/natural=water nwr/waterway=river,canal,stream

extract green \
  nwr/leisure=park,garden nwr/landuse=forest,meadow,grass nwr/natural=wood

extract landuse \
  nwr/landuse=residential,industrial,commercial,retail,railway

extract boundaries \
  nwr/boundary=administrative

echo "✓ 6 couches extraites"
