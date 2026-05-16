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
KNOWN_SPORTS = {"tennis", "soccer", "football", "basketball", "boules"}

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
    """Analyse un polygone de terrain : bearing, longueur, largeur.

    Stratégie :
      1. Trouver l'orientation via l'arête la plus longue.
      2. Projeter TOUS les sommets sur l'axe long et l'axe perpendiculaire.
      3. Utiliser l'étendue (max − min) de chaque projection.
    Cela corrige le cas courant où un bord de 24 m est découpé
    en plusieurs segments par des nœuds intermédiaires OSM.
    """
    ring = coords[0]
    if len(ring) < 4:
        return None

    # ── 1. Convertir tous les sommets en mètres (repère local) ──
    ref_lon, ref_lat = ring[0][0], ring[0][1]
    pts_m = []
    for p in ring[:-1]:                       # exclure la fermeture
        mx = dx_meters(ref_lon, ref_lat, p[0], p[1])
        my = dy_meters(ref_lat, p[1])
        pts_m.append((mx, my))

    if len(pts_m) < 3:
        return None

    # ── 2. Orientation : arête la plus longue ──
    edges = []
    for i in range(len(pts_m)):
        j = (i + 1) % len(pts_m)
        ex = pts_m[j][0] - pts_m[i][0]
        ey = pts_m[j][1] - pts_m[i][1]
        length = math.hypot(ex, ey)
        edges.append((length, ex, ey))

    edges.sort(key=lambda e: e[0], reverse=True)
    _, best_ex, best_ey = edges[0]
    angle_rad = math.atan2(best_ex, best_ey)  # depuis le nord, CW

    # ── 3. Projeter tous les sommets sur cet axe ──
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    proj_long = []   # projection sur l'axe long
    proj_perp = []   # projection sur l'axe perpendiculaire
    for mx, my in pts_m:
        proj_long.append(mx * sin_a + my * cos_a)
        proj_perp.append(mx * cos_a - my * sin_a)

    pitch_length = max(proj_long) - min(proj_long)
    pitch_width  = max(proj_perp) - min(proj_perp)

    # S'assurer que length ≥ width
    if pitch_width > pitch_length:
        pitch_length, pitch_width = pitch_width, pitch_length
        angle_rad += math.pi / 2

    # ── 4. Bearing → icon-rotate ──
    norm_bearing = math.degrees(angle_rad) % 180
    icon_rotate = (norm_bearing - 90) % 360
    if icon_rotate > 180:
        icon_rotate -= 360

    return {
        "bearing": round(icon_rotate, 1),
        "pitch_length": round(pitch_length, 1),
        "pitch_width": round(pitch_width, 1),
    }


def polygon_centroid(coords):
    """Centroïde géographique (lon, lat) d'un polygone."""
    ring = coords[0]
    pts = ring[:-1] if ring[0] == ring[-1] and len(ring) > 1 else ring
    if not pts:
        return None
    lon = sum(p[0] for p in pts) / len(pts)
    lat = sum(p[1] for p in pts) / len(pts)
    return [lon, lat]


def main():
    src = "leisure.json"
    with open(src) as f:
        data = json.load(f)

    features = data.get("features", [])
    new_points = []
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
        centroid = None

        if geom.get("type") == "Polygon":
            result = process_polygon(geom["coordinates"])
            centroid = polygon_centroid(geom["coordinates"])
        elif geom.get("type") == "MultiPolygon":
            best = None
            for poly in geom["coordinates"]:
                r = process_polygon(poly)
                if r and (best is None or r["pitch_length"] > best["pitch_length"]):
                    best = r
                    centroid = polygon_centroid(poly)
            result = best

        if result is None or centroid is None:
            continue

        canon = sorted(matched)[0]
        sport_render = SPORT_ALIAS.get(canon, canon)

        # Enrichir le polygone (pour le fill/outline)
        props["bearing"] = result["bearing"]
        props["pitch_length"] = result["pitch_length"]
        props["pitch_width"] = result["pitch_width"]
        props["sport_render"] = sport_render

        # Créer un Point au centroïde (pour le marquage)
        point_props = {
            "leisure": "pitch",
            "sport_render": sport_render,
            "bearing": result["bearing"],
            "pitch_length": result["pitch_length"],
            "pitch_width": result["pitch_width"],
        }
        # Copier le nom s'il existe
        if props.get("name"):
            point_props["name"] = props["name"]

        new_points.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": centroid},
            "properties": point_props,
        })

        enriched += 1

    # Ajouter les points à la collection
    features.extend(new_points)

    with open(src, "w") as f:
        json.dump(data, f, ensure_ascii=False)

    print(f"  {enriched} terrains enrichis + {len(new_points)} points centroïdes ajoutés")


if __name__ == "__main__":
    main()
