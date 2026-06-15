#!/usr/bin/env python3
"""
check_landuse_coverage.py
──────────────────────────
Compare les valeurs landuse=* réellement présentes dans l'extrait Bruxelles
avec :
  • la liste de référence du wiki OSM (Key:landuse)
  • les sous-types effectivement rendus dans map.config.yaml
    (layers.landuse.subtypes)

But : détecter automatiquement (issue #37) ce qui existe dans le pbf
mais n'a pas encore de rendu, SANS jamais générer de style pour un tag
qui n'existe pas dans les données Bxl.

Génère landuse_report.md classant chaque valeur en :
  - ✓ rendus            : configurés ET présents dans les données Bxl
  - ⚠ manquants         : présents dans Bxl mais PAS rendus -> à ajouter
  - ↪ gérés ailleurs    : présents dans Bxl, gérés par green/water
                          (forest/meadow/grass/flowerbed/basin)
  - · sans donnée       : configurés et/ou listés par le wiki OSM, mais
                          absents de l'extrait Bxl actuel -> aucun rendu
                          généré pour eux (normal, conforme à la consigne
                          "on ne rend pas ce qui n'est pas dans le pbf")

Usage :
  python3 check_landuse_coverage.py \
      --all-json _tmp_landuse_all.json \
      --config   map.config.yaml \
      --report   landuse_report.md
"""
import argparse, json, sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("✗  pip install pyyaml", file=sys.stderr); sys.exit(1)

# Valeurs landuse=* déjà gérées par d'autres couches que "landuse"
# -> normal qu'elles n'aient pas de sous-type dans layers.landuse
HANDLED_ELSEWHERE = {
    "forest":    "green (green.json, via natural=wood + landuse=forest)",
    "meadow":    "green (green.json)",
    "grass":     "green (green.json)",
    "flowerbed": "green (green.json)",
    "basin":     "water (water.json)",
}

# Référence : valeurs landuse=* documentées sur
# https://wiki.openstreetmap.org/wiki/Key:landuse
# (liste indicative, à mettre à jour si le wiki évolue)
WIKI_LANDUSE_VALUES = [
    "allotments", "aquaculture", "basin", "brownfield", "cemetery",
    "commercial", "conservation", "construction", "depot", "education",
    "farmland", "farmyard", "flowerbed", "forest", "garages", "grass",
    "greenfield", "greenhouse_horticulture", "harbour", "industrial",
    "landfill", "meadow", "military", "orchard", "plant_nursery", "port",
    "quarry", "railway", "recreation_ground", "religious", "residential",
    "retail", "salt_pond", "village_green", "vineyard", "winter_sports",
]


def load_features(path):
    """FeatureCollection standard ou NDJSON (une feature par ligne)."""
    text = Path(path).read_text()
    try:
        data = json.loads(text)
        return data.get("features", [])
    except json.JSONDecodeError:
        pass
    feats = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            feats.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return feats


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--all-json", required=True,
                   help="export osmium de nwr/landuse=* (toutes valeurs)")
    p.add_argument("--config", default="map.config.yaml")
    p.add_argument("--report", default="landuse_report.md")
    args = p.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"✗  {cfg_path} introuvable", file=sys.stderr); sys.exit(1)
    config = yaml.safe_load(cfg_path.read_text())
    configured = set((config.get("layers", {}).get("landuse", {})
                      .get("subtypes") or {}).keys())

    all_path = Path(args.all_json)
    if not all_path.exists():
        print(f"✗  {all_path} introuvable", file=sys.stderr); sys.exit(1)

    counts = {}
    for feat in load_features(all_path):
        val = (feat.get("properties") or {}).get("landuse")
        if val:
            counts[val] = counts.get(val, 0) + 1

    present = set(counts)

    rendered, missing, elsewhere, no_data = [], [], [], []

    for val in sorted(present | configured | set(WIKI_LANDUSE_VALUES)):
        cnt = counts.get(val, 0)
        is_cfg = val in configured
        is_elsewhere = val in HANDLED_ELSEWHERE

        if cnt == 0:
            no_data.append((val, is_cfg))
            continue
        if is_elsewhere:
            elsewhere.append((val, cnt))
        elif is_cfg:
            rendered.append((val, cnt))
        else:
            missing.append((val, cnt))

    lines = ["# Landuse coverage report", "",
             "Comparaison entre les `landuse=*` présents dans l'extrait "
             "Bruxelles et ceux rendus par `map.config.yaml` "
             "(cf. issue #37).", "",
             f"- ✓ rendus : {len(rendered)}",
             f"- ⚠ manquants (présents mais sans style) : {len(missing)}",
             f"- ↪ gérés par une autre couche : {len(elsewhere)}",
             f"- · sans donnée dans le pbf Bxl : {len(no_data)}", ""]

    if missing:
        lines += ["## ⚠ Présents dans Bxl mais non rendus", "",
                  "Ces valeurs existent dans le pbf mais n'ont pas de "
                  "sous-type dans `layers.landuse.subtypes` → ajouter un "
                  "rendu.", "",
                  "| landuse | features |", "| :--- | ---: |"]
        for val, cnt in sorted(missing, key=lambda x: -x[1]):
            lines.append(f"| `{val}` | {cnt} |")
        lines.append("")

    lines += ["## ✓ Rendus", "", "| landuse | features |", "| :--- | ---: |"]
    for val, cnt in sorted(rendered, key=lambda x: -x[1]):
        lines.append(f"| `{val}` | {cnt} |")
    lines.append("")

    if elsewhere:
        lines += ["## ↪ Gérés par une autre couche", "",
                  "| landuse | features | couche |", "| :--- | ---: | :--- |"]
        for val, cnt in sorted(elsewhere, key=lambda x: -x[1]):
            lines.append(f"| `{val}` | {cnt} | {HANDLED_ELSEWHERE[val]} |")
        lines.append("")

    if no_data:
        lines += ["## · Sans donnée dans le pbf Bxl", "",
                  "Configurés et/ou listés par le wiki OSM, mais absents "
                  "de l'extrait actuel — aucun rendu généré (conforme : "
                  "on ne rend pas ce qui n'existe pas dans les données).", "",
                  "| landuse | configuré dans map.config.yaml ? |",
                  "| :--- | :---: |"]
        for val, is_cfg in sorted(no_data):
            lines.append(f"| `{val}` | {'oui' if is_cfg else 'non'} |")
        lines.append("")

    Path(args.report).write_text("\n".join(lines) + "\n")

    print(f"✓  {args.report} : {len(rendered)} rendus, "
          f"{len(missing)} manquants, {len(elsewhere)} ailleurs, "
          f"{len(no_data)} sans donnée")

    if missing:
        print("⚠  landuse présents mais non rendus :",
              ", ".join(f"{v}({c})" for v, c in
                        sorted(missing, key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
