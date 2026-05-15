#!/usr/bin/env python3
"""
compute_pitch_bearing.py
────────────────────────
Post-traitement de leisure.json :
  - Pour chaque way leisure=pitch avec un sport connu,
    calcule l'orientation (bearing de l'axe long) et les dimensions.
  - Stocke bearing, pitch_length, pitch_width, sport_render dans les propriétés.

Le bearing est exprimé pour icon-rotate de MapLibre GL
(rotation-alignment=map) : degrés CW, 0 = axe long pointe vers l'est
(car le SVG est dessiné en paysage).
"""
import json
import math
import sys

# Sports supportés (extensible)
KNOWN_SPORTS = {"tennis", "soccer", "football", "basketball"}

# Alias de normalisation pour le rendu
SPORT_ALIAS = {"football": "soccer"}


def dx_meters(lon1, lat1, lon2, lat2):
    """Distance est-ouest en mètres."""
    avg_lat = math.radians((lat1 + lat2) / 2)
    return (lon2 - lon1) * 111_320 * math.cos(avg_lat)


def dy_meters(lat1, lat2):
    """Distance nord-sud en mètres."""
    return (lat2 - lat1) * 110_540


def edge_info(p1, p2):
    """Longueur (m) et bearing (° CW depuis le nord) d'un segment."""
    dx = dx_meters(p1[0], p1[1], p2[0], p2[1])
    dy = dy_meters(p1[1], p2[1])
    length = math.hypot(dx, dy)
    bearing = math.degrees(math.atan2(dx, dy)) % 360
    return length, bearing


def centroid_of_ring(ring):
    """Centroïde du polygone (pour placer l'icône)."""
    xs = [p[0] for p in ring[:-1]]
    ys = [p[1] for p in ring[:-1]]
    if not xs:
        return None, None
    return sum(xs) / len(xs), sum(ys) / len(ys)


def process_polygon(coords):
    """Analyse un polygone de terrain : bearing, longueur, largeur."""
    ring = coords[0]
    if len(ring) < 4:
        return None

    edges = [edge_info(ring[i], ring[i + 1]) for i in range(len(ring) - 1)]
    if not edges:
        return None

    # Axe long = arête la plus longue
    edges_sorted = sorted(edges, key=lambda e: e[0], reverse=True)
    long_len, long_bearing = edges_sorted[0]

    # Largeur = plus long segment à peu près perpendiculaire
    width = 0
    for seg_len, seg_bearing in edges_sorted[1:]:
        angle_diff = abs((seg_bearing - long_bearing + 90) % 180 - 90)
        if angle_diff > 30:          # ≈ perpendiculaire
            width = seg_len
            break
    if width == 0 and len(edges_sorted) > 1:
        width = edges_sorted[1][0]

    # Normaliser le bearing dans [0, 180) — un terrain est symétrique
    norm_bearing = long_bearing % 180

    # Conversion pour icon-rotate (SVG paysage : axe long = x = est)
    # rotate=0 → l'axe x du SVG pointe vers l'est
    # On veut que l'axe x s'aligne sur le bearing de l'axe long
    #   bearing est mesuré depuis le nord CW
    #   est = 90° depuis le nord
    # → icon_rotate = bearing - 90
    icon_rotate = (norm_bearing - 90) % 360
    if icon_rotate > 180:
        icon_rotate -= 360

    # Centroïde
    cx, cy = centroid_of_ring(ring)

    return {
        "bearing": round(icon_rotate, 1),
        "pitch_length": round(long_len, 1),
        "pitch_width": round(width, 1),
        "_cx": cx,
        "_cy": cy,
    }


def main():
    src = "leisure.json"
    with open(src) as f:
        data = json.load(f)

    features = data.get("features", [])
    enriched = 0

    for feat in features:
        props = feat.get("properties", {})
        if props.get("leisure") != "pitch":
            continue

        raw_sport = props.get("sport", "")
        sports = {s.strip().lower() for s in raw_sport.replace(",", ";").split(";")}
        matched = sports & KNOWN_SPORTS
        if not matched:
            continue

        geom = feat.get("geometry", {})
        result = None

        if geom.get("type") == "Polygon":
            result = process_polygon(geom["coordinates"])
        elif geom.get("type") == "MultiPolygon":
            best = None
            for poly in geom["coordinates"]:
                r = process_polygon(poly)
                if r and (best is None or r["pitch_length"] > best["pitch_length"]):
                    best = r
            result = best

        if result is None:
            continue

        # Stocker les propriétés utiles au rendu
        props["bearing"] = result["bearing"]
        props["pitch_length"] = result["pitch_length"]
        props["pitch_width"] = result["pitch_width"]

        # Sport normalisé (un seul pour le nom d'image)
        canon = sorted(matched)[0]
        props["sport_render"] = SPORT_ALIAS.get(canon, canon)

        enriched += 1

    with open(src, "w") as f:
        json.dump(data, f, ensure_ascii=False)

    print(f"  {enriched} terrains enrichis (bearing + dimensions)")


if __name__ == "__main__":
    main()
