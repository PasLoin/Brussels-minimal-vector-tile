#!/usr/bin/env python3
"""
compute_building_coverage.py
─────────────────────────────
Détecte les bâtiments (building=*) entièrement recouverts par leurs
building:part=yes, afin de ne PAS les rendre en 3D (silhouette
dédoublée / z-fighting avec les parties détaillées). Issue #40.

Deux méthodes, relation prioritaire sur géométrie :

  1. Relation explicite type=building (Simple 3D Buildings) :
     un membre role=outline + au moins un membre role=part
     -> l'outline est CERTAIN d'être couvert (déclaration explicite).
     Correspondance via les attributs OSM bruts @id/@type, exportés
     par `osmium export --attributes=id,type` (PAS --add-unique-id,
     qui double l'id des aires issues de ways fermés).

  2. Heuristique géométrique : aire d'intersection entre l'union des
     building:part intersectant le bâtiment et le bâtiment lui-même,
     rapportée à l'aire du bâtiment. Si le ratio dépasse --threshold
     (0.90 par défaut), le bâtiment est considéré comme couvert.

Écrit en retour, dans chaque feature de buildings_detail.json :
  - "covered_by_parts" : "yes" / "no"
  - "covered_by_parts_source" : "relation" / "geometry" (si couvert)

Le rendu 2D (buildings-fill/buildings-outline) reste inchangé pour
TOUS les bâtiments — seule la couche 3D (buildings-3d) filtre sur
covered_by_parts (cf. build_map.py).

Usage :
  python3 compute_building_coverage.py \
      --buildings buildings_detail.json \
      --parts     building_parts.json \
      --relations _tmp_building_rel.osm \
      --threshold 0.90
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from shapely.geometry import shape
    from shapely.ops import unary_union
    from shapely.strtree import STRtree
except ImportError:
    print("✗  pip install shapely", file=sys.stderr)
    sys.exit(1)


def parse_relation_outline_way_ids(osm_xml_path):
    """
    Parse un .osm (XML) filtré sur r/type=building et retourne
    l'ensemble des IDs de way (entiers, IDs OSM bruts) membres
    role=outline d'une relation qui a AUSSI au moins un membre
    role=part.
    """
    outline_ids = set()
    if not osm_xml_path or not Path(osm_xml_path).exists():
        return outline_ids

    try:
        tree = ET.parse(osm_xml_path)
    except ET.ParseError as e:
        print(f"⚠  {osm_xml_path} illisible ({e}) — relations ignorées", file=sys.stderr)
        return outline_ids

    n_relations = 0
    for relation in tree.getroot().findall("relation"):
        n_relations += 1
        is_building_type = any(
            tag.get("k") == "type" and tag.get("v") == "building"
            for tag in relation.findall("tag")
        )
        if not is_building_type:
            continue

        outline_refs, has_part = [], False
        for member in relation.findall("member"):
            if member.get("type") != "way":
                continue
            role = member.get("role")
            ref = member.get("ref")
            if role == "outline" and ref:
                try:
                    outline_refs.append(int(ref))
                except ValueError:
                    continue
            elif role == "part":
                has_part = True

        if has_part:
            outline_ids.update(outline_refs)

    print(f"  {n_relations} relations type=building lues, "
          f"{len(outline_ids)} outlines couverts par relation")
    return outline_ids


def load_features(path):
    if not path or not Path(path).exists():
        return []
    with open(path) as f:
        data = json.load(f)
    return data.get("features", [])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--buildings", default="buildings_detail.json")
    p.add_argument("--parts",     default="building_parts.json")
    p.add_argument("--relations", default=None,
                    help=".osm XML filtré sur r/type=building (optionnel)")
    p.add_argument("--threshold", type=float, default=0.90)
    args = p.parse_args()

    buildings_path = Path(args.buildings)
    if not buildings_path.exists():
        print(f"✗  {buildings_path} introuvable", file=sys.stderr)
        sys.exit(1)

    # ── 1. Relations explicites type=building (outline + part) ──────
    relation_outline_ids = parse_relation_outline_way_ids(args.relations)

    # ── 2. Index spatial des building:part ───────────────────────────
    part_features = load_features(args.parts)
    part_geoms = []
    for feat in part_features:
        try:
            g = shape(feat["geometry"])
            if not g.is_valid:
                g = g.buffer(0)
            if not g.is_empty:
                part_geoms.append(g)
        except Exception:
            continue
    tree = STRtree(part_geoms) if part_geoms else None
    print(f"  {len(part_geoms)} building:part valides indexés")

    # ── 3. Bâtiments ───────────────────────────────────────────────
    with open(buildings_path) as f:
        data = json.load(f)
    features = data.get("features", [])

    n_relation, n_geometry, n_total = 0, 0, len(features)

    for feat in features:
        props = feat.setdefault("properties", {})

        # Correspondance par relation : nécessite @id/@type bruts
        # (osmium export --attributes=id,type).
        way_id = props.get("@id")
        way_type = props.get("@type")
        matched_relation = False
        if way_type == "way" and way_id is not None:
            try:
                matched_relation = int(way_id) in relation_outline_ids
            except (TypeError, ValueError):
                matched_relation = False

        if matched_relation:
            props["covered_by_parts"] = "yes"
            props["covered_by_parts_source"] = "relation"
            n_relation += 1
            continue

        covered = False
        if tree is not None:
            try:
                bgeom = shape(feat["geometry"])
                if not bgeom.is_valid:
                    bgeom = bgeom.buffer(0)
                if not bgeom.is_empty and bgeom.area > 0:
                    candidates = tree.query(bgeom)
                    relevant = [part_geoms[i] for i in candidates
                                if part_geoms[i].intersects(bgeom)]
                    if relevant:
                        union_parts = unary_union(relevant)
                        ratio = union_parts.intersection(bgeom).area / bgeom.area
                        covered = ratio >= args.threshold
            except Exception:
                covered = False

        if covered:
            props["covered_by_parts"] = "yes"
            props["covered_by_parts_source"] = "geometry"
            n_geometry += 1
        else:
            props["covered_by_parts"] = "no"

    with open(buildings_path, "w") as f:
        json.dump(data, f, ensure_ascii=False)

    n_covered = n_relation + n_geometry
    pct = round(100 * n_covered / n_total) if n_total else 0
    print(f"✓  {buildings_path} : {n_covered}/{n_total} bâtiments couverts "
          f"({pct}%) — {n_relation} via relation, {n_geometry} via géométrie "
          f"(seuil {args.threshold:.0%})")


if __name__ == "__main__":
    main()
