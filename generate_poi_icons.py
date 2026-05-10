#!/usr/bin/env python3
"""
generate_poi_icons.py
─────────────────────
Lit poi.json, auto-détecte les tag-keys OSM présents (amenity, shop,
tourism, craft, leisure…), vérifie les icônes disponibles (local / CDN),
et génère :
  • www/poi-icons.json   — mapping + métadonnées pour index.html
  • missing-icons.txt    — types POI sans icône locale (triés par usage)

Le JSON de sortie contient une clé _meta avec les keys détectés :
index.html construit dynamiquement l'expression icon-image à partir
de cette liste → plus besoin de modifier style.json quand on ajoute
un nouveau type dans generate_json.bash.

Usage :
  python3 generate_poi_icons.py                     # depuis la racine du projet
  python3 generate_poi_icons.py --poi-json poi.json # chemin explicite
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

# ═══════════════════════════════════════════════════════════
# CDN bases  (même ordre de priorité que index.html)
# ═══════════════════════════════════════════════════════════
LOCAL_DIR   = os.path.join('www', 'assets', 'icons')
TEMAKI_URL  = 'https://cdn.jsdelivr.net/npm/@ideditor/temaki@5/icons/{}.svg'
MAKI_URL    = 'https://cdn.jsdelivr.net/npm/@mapbox/maki/icons/{}.svg'
LIBERTY_URL = 'https://raw.githubusercontent.com/maputnik/osm-liberty/gh-pages/icons/{}.svg'

# ═══════════════════════════════════════════════════════════
# Tag-keys OSM qui représentent un « type » de POI.
# On ne scanne que ceux-ci dans les properties.
# Liste large — seuls ceux effectivement présents dans les
# données seront retenus dans le JSON de sortie.
# ═══════════════════════════════════════════════════════════
OSM_TYPE_KEYS = {
    'amenity', 'shop', 'tourism', 'craft', 'leisure', 'office',
    'healthcare', 'historic', 'emergency', 'club', 'man_made',
    'natural', 'aeroway', 'military', 'telecom', 'advertising',
    'industrial', 'gambling',
}

# ═══════════════════════════════════════════════════════════
# Sous-types : clés OSM dont les valeurs méritent une icône
# spécifique.  Le script scanne automatiquement toutes les
# valeurs présentes dans les données et génère un type
# synthétique « {key}-{value} » (ex: cuisine-friture,
# religion-muslim).  Il suffit de déposer l'icône SVG dans
# www/assets/icons/ avec le nom {key}_{value}.svg
# (ex: cuisine_friture.svg, religion_muslim.svg).
# ═══════════════════════════════════════════════════════════
SUB_TYPE_KEYS = {'cuisine', 'religion'}

# ═══════════════════════════════════════════════════════════
# Mapping OSM tag value → CDN icon name quand ils diffèrent
# ═══════════════════════════════════════════════════════════
CDN_NAME_OVERRIDES = {
    # amenity
    'pub':               {'maki': 'beer', 'liberty': 'pub'},
    'fast_food':         {'maki': 'fast-food', 'liberty': 'fast-food'},
    'clinic':            {'temaki': 'stethoscope', 'maki': 'doctor', 'liberty': 'hospital'},
    'doctor':            {'temaki': 'stethoscope', 'maki': 'doctor', 'liberty': 'health'},
    'dentist':           {'temaki': 'tooth', 'maki': None, 'liberty': 'dentist'},
    'university':        {'maki': 'college', 'liberty': 'university'},
    'post_office':       {'temaki': 'post_box', 'maki': 'post', 'liberty': 'post'},
    'place_of_worship':  {'temaki': 'place_of_worship', 'maki': 'religious-christian', 'liberty': 'place-of-worship'},
    'townhall':          {'temaki': 'town_hall', 'maki': 'town-hall', 'liberty': 'town-hall'},
    'courthouse':        {'temaki': 'court', 'maki': None, 'liberty': 'courthouse'},
    'community_centre':  {'temaki': 'community', 'maki': None, 'liberty': 'community-centre'},
    'fire_station':      {'maki': 'fire-station', 'liberty': 'fire-station'},
    # tourism
    'hotel':             {'maki': 'lodging', 'liberty': 'hotel'},
    'hostel':            {'temaki': 'bed', 'maki': 'lodging', 'liberty': 'hostel'},
    'viewpoint':         {'temaki': 'binoculars', 'maki': 'viewpoint', 'liberty': 'viewpoint'},
    # shops
    'supermarket':       {'maki': 'grocery', 'liberty': 'supermarket'},
    'convenience':       {'temaki': 'convenience', 'maki': 'grocery', 'liberty': 'convenience'},
    'clothes':           {'temaki': 'clothes', 'maki': 'clothing-store', 'liberty': 'clothing-store'},
    'jewelry':           {'temaki': 'jewelry', 'maki': 'jewelry-store', 'liberty': 'jewelry-store'},
    'mobile_phone':      {'temaki': 'mobile_phone', 'maki': None, 'liberty': 'mobile-phone'},
    'dry_cleaning':      {'temaki': 'dry_cleaning', 'maki': None, 'liberty': 'laundry'},
    'department_store':  {'temaki': 'department_store', 'maki': 'department-store', 'liberty': 'department-store'},
    'doityourself':      {'temaki': 'doityourself', 'maki': None, 'liberty': 'hardware'},
    'car_repair':        {'temaki': 'car_repair', 'maki': 'car', 'liberty': 'car-repair'},
    'alcohol':           {'temaki': 'alcohol', 'maki': 'alcohol-shop', 'liberty': 'alcohol-shop'},
    'pet':               {'temaki': 'pet', 'maki': None, 'liberty': 'pet-shop'},
    'travel_agency':     {'temaki': 'travel_agency', 'maki': None, 'liberty': 'travel-agency'},
    'books':             {'temaki': 'books', 'maki': None, 'liberty': 'library'},
    # special
    'cuisine-friture':   {'local': 'cuisine_friture', 'temaki': None, 'maki': None, 'liberty': None},
}


def check_url(url, timeout=8):
    """HEAD-request rapide, retourne True si 200."""
    try:
        req = urllib.request.Request(url, method='HEAD')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def check_local(name):
    """Vérifie si www/assets/icons/{name}.svg existe.
    Essaie aussi avec underscores (cuisine-friture → cuisine_friture)."""
    if os.path.isfile(os.path.join(LOCAL_DIR, f'{name}.svg')):
        return name
    alt = name.replace('-', '_')
    if alt != name and os.path.isfile(os.path.join(LOCAL_DIR, f'{alt}.svg')):
        return alt
    return None


def resolve_icon(poi_type):
    """
    Pour un type POI donné, retourne un tuple :
      (poi_type, [local, temaki, maki, liberty])
    """
    overrides = CDN_NAME_OVERRIDES.get(poi_type, {})

    local_name = overrides.get('local', poi_type)
    local = check_local(local_name)

    temaki_name = overrides.get('temaki', poi_type)
    if temaki_name is None:
        temaki = None
    elif check_url(TEMAKI_URL.format(temaki_name)):
        temaki = temaki_name
    else:
        temaki = None

    maki_name = overrides.get('maki', poi_type)
    if maki_name is None:
        maki = None
    elif check_url(MAKI_URL.format(maki_name)):
        maki = maki_name
    else:
        maki = None

    liberty_name = overrides.get('liberty', poi_type)
    if liberty_name is None:
        liberty = None
    elif check_url(LIBERTY_URL.format(liberty_name)):
        liberty = liberty_name
    else:
        liberty = None

    return poi_type, [local, temaki, maki, liberty]


def extract_poi_types(poi_json_path):
    """
    Lit poi.json et retourne :
      - types : Counter { type_name: count }
      - detected_keys : set des tag-keys OSM effectivement trouvés
      - sub_types : dict { icon_key: {key, value} } pour les sous-types détectés
    Auto-détecte les keys depuis OSM_TYPE_KEYS et SUB_TYPE_KEYS.
    """
    types = Counter()
    detected_keys = set()
    sub_types = {}  # 'cuisine-friture' → {'key': 'cuisine', 'value': 'friture'}

    with open(poi_json_path) as f:
        data = json.load(f)

    features = data.get('features', [])
    for feat in features:
        props = feat.get('properties', {})

        # Sous-types auto-détectés (cuisine, religion, denomination…)
        for key in SUB_TYPE_KEYS:
            val = props.get(key)
            if val and isinstance(val, str) and val.strip():
                val = val.strip()
                icon_key = f'{key}-{val}'
                types[icon_key] += 1
                sub_types[icon_key] = {'key': key, 'value': val}

        # Type keys principaux
        for key in OSM_TYPE_KEYS:
            val = props.get(key)
            if val and isinstance(val, str) and val.strip():
                types[val.strip()] += 1
                detected_keys.add(key)

    return types, detected_keys, sub_types


def main():
    parser = argparse.ArgumentParser(description='Génère poi-icons.json et missing-icons.txt')
    parser.add_argument('--poi-json', default='poi.json',
                        help='Chemin vers poi.json (défaut: poi.json)')
    parser.add_argument('--output', default=os.path.join('www', 'poi-icons.json'),
                        help='Chemin de sortie JSON (défaut: www/poi-icons.json)')
    parser.add_argument('--missing', default='missing-icons.txt',
                        help='Chemin du fichier missing-icons (défaut: missing-icons.txt)')
    parser.add_argument('--workers', type=int, default=10,
                        help='Nombre de threads pour les vérifications CDN (défaut: 10)')
    args = parser.parse_args()

    if not os.path.isfile(args.poi_json):
        print(f'✗ {args.poi_json} introuvable. Lancez d\'abord generate_json.bash', file=sys.stderr)
        sys.exit(1)

    # ── 1. Extraire les types POI ──────────────────────────
    print(f'→ Lecture de {args.poi_json}...')
    poi_types, detected_keys, sub_types = extract_poi_types(args.poi_json)
    print(f'  {len(poi_types)} types POI trouvés ({sum(poi_types.values())} features)')
    print(f'  Tag-keys détectés : {", ".join(sorted(detected_keys))}')
    if sub_types:
        print(f'  Sous-types détectés : {len(sub_types)} ({", ".join(sorted(SUB_TYPE_KEYS & {st["key"] for st in sub_types.values()}))})')

    # Toujours inclure le fallback "shop" (icône générique pour les shops inconnus)
    if 'shop' not in poi_types:
        poi_types['shop'] = 0

    # ── 2. Résoudre les icônes en parallèle ────────────────
    print(f'→ Vérification des icônes ({len(poi_types)} types, {args.workers} threads)...')
    icons = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(resolve_icon, t): t for t in sorted(poi_types)}
        for future in as_completed(futures):
            poi_type, sources = future.result()
            icons[poi_type] = sources
            has_any = any(s is not None for s in sources)
            status = '✓' if has_any else '✗'
            count = poi_types[poi_type]
            print(f'  {status} {poi_type} ({count}x) → {sources}')

    # ── 3. Générer poi-icons.json ──────────────────────────
    # special_cases : seulement les sous-types qui ont au moins une icône
    special_cases = []
    for icon_key, info in sorted(sub_types.items()):
        if icon_key in icons and any(s is not None for s in icons[icon_key]):
            special_cases.append({
                'key': info['key'],
                'value': info['value'],
                'icon_key': icon_key,
            })

    output = {
        '_meta': {
            'type_keys': sorted(detected_keys),
            'special_cases': special_cases,
        },
    }
    for t in sorted(icons):
        output[t] = icons[t]

    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    has_icon = sum(1 for s in icons.values() if any(x is not None for x in s))
    print(f'✓ {args.output} : {has_icon}/{len(icons)} types avec icône')

    # ── 4. Générer missing-icons.txt ───────────────────────
    # Trié par nombre d'occurrences décroissant pour prioriser
    missing = []
    for poi_type, sources in icons.items():
        if sources[0] is None:
            count = poi_types.get(poi_type, 0)
            has_cdn = any(s is not None for s in sources[1:])
            missing.append((poi_type, count, has_cdn))

    missing.sort(key=lambda x: -x[1])

    with open(args.missing, 'w') as f:
        for poi_type, count, has_cdn in missing:
            cdn_note = '' if has_cdn else '  # aucun CDN non plus'
            f.write(f'{poi_type}.svg ({count}x){cdn_note}\n')

    print(f'✓ {args.missing} : {len(missing)} icônes locales manquantes')

    # ── 5. Résumé ─────────────────────────────────────────
    no_icon_at_all = [t for t, s in icons.items() if not any(x is not None for x in s)]
    if no_icon_at_all:
        print(f'\n⚠ {len(no_icon_at_all)} types sans icône nulle part :')
        for t in sorted(no_icon_at_all, key=lambda t: -poi_types.get(t, 0)):
            print(f'  - {t} ({poi_types[t]} features)')


if __name__ == '__main__':
    main()
