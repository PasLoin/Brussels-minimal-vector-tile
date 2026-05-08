#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Extraction minimaliste — 11 couches essentielles
# Pré-requis : osmium-tool, jq
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
  nwr/highway=motorway,trunk,trunk_link,primary,primary_link,secondary,secondary_link,tertiary,tertiary_link,residential,living_street,unclassified,service,track,busway nwr/man_made=bridge,tunnel

# Buildings : nwr/building=* inclut les relations ET leurs ways membres
extract buildings nwr/building=*

extract water \
  nwr/natural=water nwr/waterway=river,canal,stream,ditch nwr/landuse=basin nwr/natural=wetland

extract green \
  nwr/landuse=flowerbed nwr/natural=shrubbery nwr/natural=scrub \
  nwr/leisure=park,garden nwr/landuse=forest,meadow,grass nwr/natural=wood

extract trees \
  nwr/natural=tree nwr/natural=tree_row nwr/barrier=hedge  

extract landuse \
  nwr/landuse=residential,industrial,commercial,retail,railway,education,construction,brownfield,greenfield,landfill

extract boundaries \
  nwr/boundary=administrative

extract poi \
  nwr/shop=* \
  nwr/amenity=restaurant,cafe,bar,pub,fast_food,bank,pharmacy,hospital,clinic,school,university,library,theatre,cinema,post_office,police,fire_station \
  nwr/tourism=hotel,hostel,museum,attraction,information,viewpoint

# ── Dédoublonnage POI ────────────────────────────────────
# osmium export peut produire des doublons pour les ways :
# 1. LineString + Polygon du même way (closed way)
# 2. Polygon du way + MultiPolygon de sa relation parente
# On filtre les LineString, dédoublonne par @id ET par
# empreinte géométrique (coordonnées arrondies).
echo "  → dédoublonnage POI"
python3 << 'DEDUP'
import json

prio = {'MultiPolygon': 3, 'Polygon': 3, 'Point': 2}

def geom_hash(geom):
    """Hash stable d'une géométrie (arrondi 6 décimales)."""
    def flatten(c):
        if isinstance(c, (int, float)):
            return (round(c, 6),)
        result = ()
        for item in c:
            result += flatten(item)
        return result
    return (geom['type'],) + flatten(geom.get('coordinates', []))

seen_id = {}    # @id → feature  (même way exporté 2×)
seen_geo = {}   # geom_hash → @id (way + sa relation parente)

with open('poi.json') as f:
    collection = json.load(f)

before = len(collection.get('features', []))
kept = []

for feat in collection.get('features', []):
    gt = feat['geometry']['type']
    if gt not in prio:
        continue                           # skip LineString / MultiLineString

    fid = feat.get('properties', {}).get('@id', '')

    # ── Dedup par @id ──
    if fid and fid in seen_id:
        prev_gt = seen_id[fid]['geometry']['type']
        if prio[gt] <= prio.get(prev_gt, 0):
            continue

    # ── Dedup par géométrie (way/X vs relation/Y, même contour) ──
    gh = geom_hash(feat['geometry'])
    if gh in seen_geo and seen_geo[gh] != fid:
        # Même géométrie, @id différent → garder celui de plus haute priorité
        existing_fid = seen_geo[gh]
        if existing_fid in seen_id:
            existing_prio = prio.get(seen_id[existing_fid]['geometry']['type'], 0)
            if prio[gt] <= existing_prio:
                continue
            # Nouveau est meilleur → retirer l'ancien
            kept[:] = [f for f in kept if f.get('properties', {}).get('@id', '') != existing_fid]
            del seen_id[existing_fid]

    if fid:
        seen_id[fid] = feat
    seen_geo[gh] = fid
    kept.append(feat)

collection['features'] = kept
after = len(kept)

with open('poi.json', 'w') as out:
    json.dump(collection, out, ensure_ascii=False)

print(f'  {before} → {after} features ({before - after} doublons supprimés)')
DEDUP

extract pedestrian \
  nwr/highway=pedestrian,footway,path,steps

extract cycleway \
  nwr/highway=cycleway

extract railway \
  nwr/railway=rail,tram,subway,miniature

# ── Transport public STIB/MIVB ──────────────────────────
# osmium export ignore les relations type=route
# → osmium cat en XML + parsing Python (stdlib, zéro dépendance)
echo "→ public_transport (relations STIB/MIVB)"
osmium tags-filter "$SRC" r/route=bus,tram,subway,trolleybus -o "_tmp_pt.osm.pbf" --overwrite
osmium cat "_tmp_pt.osm.pbf" -o "_tmp_pt.osm" --overwrite
python3 extract_stib_routes.py
rm -f _tmp_pt.osm.pbf _tmp_pt.osm
echo "  $(wc -l < "public_transport.json") lignes"

echo "✓ 11 couches extraites"
