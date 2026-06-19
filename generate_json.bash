#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Extraction minimaliste — 14 couches essentielles
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
  nwr/highway=motorway,motorway_link,trunk,trunk_link,primary,primary_link,secondary,secondary_link,tertiary,tertiary_link,residential,living_street,unclassified,service,track,busway nwr/man_made=bridge,tunnel

# ── Buildings ──────────────────────────────────────────────
# -a id,type (issue #40) : ajoute les propriétés @id/@type avec l'ID
# OSM BRUT du way (pas de transformation). Nécessaire pour faire
# correspondre les bâtiments aux membres "outline" des relations
# type=building (cf. compute_building_coverage.py). On évite
# volontairement --add-unique-id=type_id : pour les aires issues de
# ways fermés, osmium DOUBLE l'id (id_unique = 2 × id_original),
# ce qui casserait silencieusement la correspondance.
# --geometry-types=polygon : sans ça, osmium export émet AUSSI une
# version LineString de chaque way fermée (comportement documenté
# par défaut), créant un doublon Polygon+LineString pour le même
# bâtiment dans les tuiles. On ne veut que les polygones ici.
echo "→ buildings"
osmium tags-filter "$SRC" nwr/building=* -o "_tmp_buildings.osm.pbf" --overwrite
osmium export "_tmp_buildings.osm.pbf" -o "buildings.json" --overwrite \
  --attributes=id,type --geometry-types=polygon
rm -f "_tmp_buildings.osm.pbf"
echo "  $(wc -l < "buildings.json") lignes"
echo "  → copie buildings.json → buildings_detail.json (avant merge)"
cp buildings.json buildings_detail.json

# lod=detail : marqueur explicite, symétrique de lod=merged ajouté par
# merge_buildings.py (issue z15-18 leak). Permet au style de filtrer
# buildings-3d sur ce critère plutôt que de dépendre des tranches de
# zoom tippecanoe, qui peuvent laisser fuiter une feature au-delà de
# sa plage prévue.
python3 << 'TAG_DETAIL'
import json
with open('buildings_detail.json') as f:
    data = json.load(f)
for feat in data.get('features', []):
    feat.setdefault('properties', {})['lod'] = 'detail'
with open('buildings_detail.json', 'w') as f:
    json.dump(data, f, ensure_ascii=False)
print(f"  {len(data.get('features', []))} features taguées lod=detail")
TAG_DETAIL

# ── Building parts (issue #40 : rendu 3D détaillé) ───────────────
# Pas de fusion via merge_buildings.py : chaque partie garde sa
# propre hauteur/min_height (toits étagés, tours...), les fusionner
# détruirait cette info. Chargé à la demande uniquement en mode 3D
# (cf. www/index.html), jamais référencé dans style.json.
# --geometry-types=polygon : même raison que pour buildings ci-dessus.
echo "→ building_parts"
osmium tags-filter "$SRC" wr/building:part=yes -o "_tmp_building_parts.osm.pbf" --overwrite
osmium export "_tmp_building_parts.osm.pbf" -o "building_parts.json" --overwrite \
  --attributes=id,type --geometry-types=polygon
rm -f "_tmp_building_parts.osm.pbf"
echo "  $(wc -l < "building_parts.json") lignes"

# ── Relations type=building (cas complexes, issue #40) ───────────
# Spec Simple 3D Buildings : une relation type=building avec des
# membres role=outline (le contour) et role=part (les volumes
# détaillés). On extrait juste la LISTE des membres (id+rôle), pas de
# géométrie — un objet relation porte toujours sa liste de membres
# intrinsèquement, qu'on garde ou non les ways/nodes référencés.
echo "→ relations type=building (cas complexes)"
osmium tags-filter "$SRC" r/type=building -o "_tmp_building_rel.osm.pbf" --overwrite
osmium cat "_tmp_building_rel.osm.pbf" -o "_tmp_building_rel.osm" --overwrite
REL_COUNT=$(grep -c "<relation" "_tmp_building_rel.osm" 2>/dev/null || echo 0)
echo "  ${REL_COUNT} relations type=building trouvées"

# ── Détection des bâtiments entièrement couverts par leurs parties ──
# Relation explicite en priorité, sinon heuristique géométrique ≥90%
# (cf. issue #40). Mute buildings_detail.json en place (ajoute
# covered_by_parts / covered_by_parts_source). @id/@type sont
# nécessaires À CETTE ÉTAPE pour la correspondance avec les relations.
python3 compute_building_coverage.py \
  --buildings buildings_detail.json \
  --parts     building_parts.json \
  --relations _tmp_building_rel.osm \
  --threshold 0.90 \
  || echo "⚠  compute_building_coverage.py en échec (non bloquant — buildings-3d affichera tout)"
rm -f _tmp_building_rel.osm.pbf _tmp_building_rel.osm

# ── Nettoyage des propriétés de build uniquement ─────────────────
# @id/@type n'ont servi que pour la correspondance avec les relations
# type=building ci-dessus, et covered_by_parts_source n'est qu'une
# info de debug jamais lue par style.json (seuls "lod" et
# "covered_by_parts" sont effectivement utilisés par build_map.py).
# On les retire avant tippecanoe : aucune perte fonctionnelle, fichier
# final plus léger.
python3 << 'STRIP_BUILD_PROPS'
import json
with open('buildings_detail.json') as f:
    data = json.load(f)
removed = 0
for feat in data.get('features', []):
    props = feat.get('properties', {})
    for k in ('@id', '@type', 'covered_by_parts_source'):
        if k in props:
            del props[k]
            removed += 1
with open('buildings_detail.json', 'w') as f:
    json.dump(data, f, ensure_ascii=False)
print(f"  {removed} propriétés de build retirées (@id/@type/covered_by_parts_source)")
STRIP_BUILD_PROPS

extract water \
  nwr/natural=water nwr/waterway=river,canal,stream,ditch nwr/landuse=basin nwr/natural=wetland

extract green \
  nwr/landuse=flowerbed nwr/natural=shrubbery nwr/natural=scrub \
  nwr/leisure=park,garden nwr/landuse=forest,meadow,grass nwr/natural=wood \
  nwr/natural=grassland,heath

extract trees \
  nwr/natural=tree nwr/natural=tree_row nwr/barrier=hedge  

extract landuse \
  nwr/landuse=residential,industrial,commercial,retail,railway,education,construction,brownfield,greenfield,landfill,military,cemetery,allotments,farmland,farmyard,garages,religious,recreation_ground,village_green,quarry,depot

# ── Vérification de couverture landuse (issue #37) ───────
# Extraction large landuse=* (toutes valeurs) pour comparer ce qui
# existe vraiment dans Bxl vs le wiki OSM et map.config.yaml.
# Fichier temporaire uniquement — pas utilisé pour le rendu, afin
# de ne pas dupliquer les features déjà couvertes par green/water.
echo "→ landuse coverage check (vs wiki + map.config.yaml)"
osmium tags-filter "$SRC" nwr/landuse=* -o "_tmp_landuse_all.osm.pbf" --overwrite
osmium export "_tmp_landuse_all.osm.pbf" -o "_tmp_landuse_all.json" --overwrite
python3 check_landuse_coverage.py \
  --all-json _tmp_landuse_all.json \
  --config   map.config.yaml \
  --report   landuse_report.md \
  || echo "⚠  landuse coverage check en échec (non bloquant)"
rm -f _tmp_landuse_all.osm.pbf _tmp_landuse_all.json

extract boundaries \
  nwr/boundary=administrative

# ── Mobilier urbain / micro-mapping (issue #51) ──────────
# Géométrie native conservée — contrairement à poi.json, AUCUNE
# conversion en points n'est appliquée ici : barrier=fence reste une
# LineString (rendue en ligne dans build_map.py), tout le reste
# (bench, bollard, gate, street_lamp, entrance...) reste un Point.
# n/entrance=* : restreint aux nodes (usage quasi exclusif de ce tag).
extract street_furniture \
  nwr/amenity=bench,lounger,waste_basket,vending_machine \
  nwr/barrier=bollard,gate,bus_trap,cycle_barrier,lift_gate,planter,fence \
  nwr/highway=street_lamp \
  n/entrance=*

# ── Vérification de couverture street_furniture (issue #51) ──────
# Même principe que la vérification landuse (issue #37) : extraction
# élargie (valeurs déjà rendues + candidats du wiki OSM pas encore
# configurés) pour que le rapport distingue "présent mais non rendu"
# de "absent du pbf Bxl". Fichier temporaire uniquement — pas utilisé
# pour le rendu (street_furniture.json ci-dessus reste limité aux tags
# explicitement configurés dans map.config.yaml).
echo "→ street_furniture coverage check (vs wiki + map.config.yaml)"
osmium tags-filter "$SRC" \
  nwr/amenity=bench,lounger,waste_basket,vending_machine,drinking_water,clock,bicycle_parking,shelter,give_box \
  nwr/barrier=bollard,gate,bus_trap,cycle_barrier,lift_gate,planter,fence,kissing_gate,block,full-height_turnstile,swing_gate,stile \
  nwr/highway=street_lamp \
  n/entrance=* \
  -o "_tmp_street_furniture_all.osm.pbf" --overwrite
osmium export "_tmp_street_furniture_all.osm.pbf" -o "_tmp_street_furniture_all.json" --overwrite
python3 check_street_furniture_coverage.py \
  --all-json _tmp_street_furniture_all.json \
  --config   map.config.yaml \
  --report   street_furniture_report.md \
  || echo "⚠  street_furniture coverage check en échec (non bloquant)"
rm -f _tmp_street_furniture_all.osm.pbf _tmp_street_furniture_all.json

# POI : extraction séparée avec --add-unique-id pour le dédoublonnage
echo "→ poi"
osmium tags-filter "$SRC" \
  nwr/shop=* \
  nwr/amenity=restaurant,cafe,bar,pub,fast_food,bank,pharmacy,hospital,clinic,school,university,library,theatre,cinema,post_office,police,fire_station,doctor,dentist,place_of_worship,townhall,courthouse,community_centre,kindergarten,veterinary \
  nwr/tourism=hotel,hostel,museum,attraction,information,viewpoint \
  nwr/leisure=playground \
  nwr/craft=* \
  -o "_tmp_poi.osm.pbf" --overwrite
osmium export "_tmp_poi.osm.pbf" -o "poi.json" --overwrite --add-unique-id=type_id
rm -f "_tmp_poi.osm.pbf"
echo "  $(wc -l < "poi.json") lignes"

# ── Normalisation POI → points + dédoublonnage ───────────
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
normalized = 0

# Clés sous-type dont les valeurs peuvent être multiples (séparées par
# des points-virgules dans OSM). On ne conserve que la première valeur,
# présumée principale, pour garantir un mapping 1-pour-1 vers une icône
# (issue #56 : "cuisine=french;italian" cassait la résolution d'icône).
MULTI_VALUE_KEYS = ('cuisine', 'religion', 'vending', 'door')

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

    # ── Normalisation des sous-types à valeurs multiples (issue #56) ──
    # OSM autorise des valeurs séparées par des points-virgules
    # (ex: cuisine=french;italian;pizza). On ne conserve que la
    # première valeur, présumée principale, pour garantir un mapping
    # 1-pour-1 vers une icône (un seul icon-image MapLibre à la fois).
    props = feat.get('properties') or {}
    for _key in MULTI_VALUE_KEYS:
        _val = props.get(_key)
        if _val and isinstance(_val, str) and ';' in _val:
            props[_key] = _val.split(';')[0].strip()
            normalized += 1

    kept.append(feat)
    stats['pt' if was_point else 'conv'] += 1

collection['features'] = kept

with open('poi.json', 'w') as out:
    json.dump(collection, out, ensure_ascii=False)

print(f"  {before} → {len(kept)} POI "
      f"({stats['pt']} points, {stats['conv']} surfaces→centroïde, "
      f"{stats['dup']} doublons, {stats['skip']} ignorés, "
      f"{normalized} valeurs multi-cuisine/religion/vending/door normalisées)")
POI_POINTS

extract leisure \
  nwr/leisure=playground,pitch,fitness_station,dog_park,outdoor_seating

# ── Orientation des terrains de sport ────────────────────
echo "  → calcul orientation des terrains de sport"
python3 compute_pitch_bearing.py

extract pedestrian \
  nwr/highway=pedestrian,footway,path,steps

extract cycleway \
  nwr/highway=cycleway

extract railway \
  nwr/railway=rail,tram,subway,miniature

# ── Transport public STIB/MIVB ──────────────────────────
echo "→ public_transport (relations STIB/MIVB)"
osmium tags-filter "$SRC" r/route=bus,tram,subway,trolleybus -o "_tmp_pt.osm.pbf" --overwrite
osmium cat "_tmp_pt.osm.pbf" -o "_tmp_pt.osm" --overwrite
python3 extract_stib_routes.py
rm -f _tmp_pt.osm.pbf _tmp_pt.osm
echo "  $(wc -l < "public_transport.json") lignes"

echo "✓ 14 couches extraites (+ buildings_detail.json pour zoom haut)"
