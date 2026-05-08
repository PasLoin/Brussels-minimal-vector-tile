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

# POI : extraction séparée avec --add-unique-id pour le dédoublonnage
echo "→ poi"
osmium tags-filter "$SRC" \
  nwr/shop=* \
  nwr/amenity=restaurant,cafe,bar,pub,fast_food,bank,pharmacy,hospital,clinic,school,university,library,theatre,cinema,post_office,police,fire_station \
  nwr/tourism=hotel,hostel,museum,attraction,information,viewpoint \
  -o "_tmp_poi.osm.pbf" --overwrite
osmium export "_tmp_poi.osm.pbf" -o "poi.json" --overwrite --add-unique-id=type_id
rm -f "_tmp_poi.osm.pbf"
echo "  $(wc -l < "poi.json") lignes"

# ── Normalisation POI → points + dédoublonnage ───────────
# 1. Un POI polygone chevauche plusieurs tuiles → Tippecanoe le
#    découpe → MapLibre place un symbole par fragment.
#    Fix : convertir les surfaces en point centroïde AVANT tippecanoe.
# 2. osmium export peut dupliquer un même way en 2 features.
#    --add-unique-id=type_id met un id unique (ex: "w15248") dans
#    feature.id → dedup fiable.
echo "  → normalisation POI en points + dédoublonnage"
python3 << 'POI_POINTS'
import json


def ring_area_and_centroid(ring):
    """Signed area and centroid for a coordinate ring."""
    if len(ring) < 3:
        return 0.0, None
    area2, cx, cy = 0.0, 0.0, 0.0
    pts = ring if ring[0] == ring[-1] else ring + [ring[0]]
    for (x1, y1, *_), (x2, y2, *_) in zip(pts, pts[1:]):
        cross = x1 * y2 - x2 * y1
        area2 += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if area2 == 0:
        return 0.0, None
    return area2 / 2.0, [cx / (3.0 * area2), cy / (3.0 * area2)]


def avg_point(coords):
    """Fallback: average of all coordinate pairs."""
    pts = []
    def collect(v):
        if isinstance(v, list) and len(v) >= 2 and isinstance(v[0], (int, float)):
            pts.append(v[:2]); return
        if isinstance(v, list):
            for i in v: collect(i)
    collect(coords)
    if not pts:
        return None
    return [sum(p[0] for p in pts) / len(pts),
            sum(p[1] for p in pts) / len(pts)]


def to_point(geom):
    """Convert any geometry to a representative point (or None)."""
    gt, coords = geom.get('type'), geom.get('coordinates')
    if gt == 'Point':
        return coords
    if gt == 'Polygon' and coords:
        _, c = ring_area_and_centroid(coords[0])
        return c or avg_point(coords)
    if gt == 'MultiPolygon' and coords:
        best, best_a = None, -1.0
        for poly in coords:
            if not poly: continue
            a, c = ring_area_and_centroid(poly[0])
            if c and abs(a) > best_a:
                best, best_a = c, abs(a)
        return best or avg_point(coords)
    return None  # LineString etc. → skip


with open('poi.json') as f:
    collection = json.load(f)

features = collection.get('features', [])
before = len(features)
seen_ids = set()
kept = []
stats = {'pt': 0, 'conv': 0, 'dup': 0, 'skip': 0}

for feat in features:
    geom = feat.get('geometry') or {}
    pt = to_point(geom)
    if pt is None:
        stats['skip'] += 1
        continue

    # ── Dedup par feature.id (osmium numeric ID) ──
    fid = feat.get('id')
    if fid is not None and fid in seen_ids:
        stats['dup'] += 1
        continue
    if fid is not None:
        seen_ids.add(fid)

    was_point = geom.get('type') == 'Point'
    feat['geometry'] = {'type': 'Point', 'coordinates': pt}
    kept.append(feat)
    stats['pt' if was_point else 'conv'] += 1

collection['features'] = kept

with open('poi.json', 'w') as out:
    json.dump(collection, out, ensure_ascii=False)

print(f"  {before} → {len(kept)} POI "
      f"({stats['pt']} points, {stats['conv']} surfaces→centroïde, "
      f"{stats['dup']} doublons, {stats['skip']} ignorés)")
POI_POINTS

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
