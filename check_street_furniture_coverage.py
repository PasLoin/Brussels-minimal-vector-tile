#!/usr/bin/env python3
"""
check_street_furniture_coverage.py
───────────────────────────────────
Compare les valeurs amenity=* / barrier=* / highway=street_lamp
réellement présentes dans l'extrait Bruxelles avec :
  • une liste de référence (mobilier urbain documenté sur le wiki OSM)
  • les sous-types effectivement rendus dans map.config.yaml
    (layers.street_furniture.subtypes)

But (issue #51) : détecter automatiquement ce qui existe dans le pbf
mais n'a pas encore de rendu, SANS jamais générer de style pour un tag
qui n'existe pas dans les données Bxl — exactement le même principe
que check_landuse_coverage.py (issue #37), appliqué au mobilier urbain
("street furniture, small object (micromapping)").

Génère street_furniture_report.md classant chaque valeur en :
  - ✓ rendus      : configurés ET présents dans les données Bxl
  - ⚠ manquants   : présents dans Bxl mais PAS configurés -> à ajouter
  - · sans donnée : configurés et/ou listés comme candidats, mais
                    absents de l'extrait Bxl actuel -> aucun rendu
                    généré pour eux (normal)

`entrance=*` est traité à part : la valeur précise (yes/home/garage/
main/service/exit/emergency…) est trop hétérogène et inconsistante
pour mériter un rendu par valeur — le mobilier "entrance" est rendu
de façon uniforme dès que la clé est présente, quelle que soit sa
valeur (cf. street_furniture() dans build_map.py). On rapporte
seulement le total de features.

`vending=*` est lui aussi traité à part : amenity=vending_machine est
déjà une couche rendue, vending=* n'est qu'un raffinement d'icône (sur
le même principe que cuisine=* / religion=* pour les POI), pas une
couche supplémentaire. Le statut des icônes se vérifie via
missing-icons.txt après generate_poi_icons.py.

Usage :
  python3 check_street_furniture_coverage.py \
      --all-json _tmp_street_furniture_all.json \
      --config   map.config.yaml \
      --report   street_furniture_report.md
"""
import argparse, json, sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("✗  pip install pyyaml", file=sys.stderr); sys.exit(1)

# Référence : valeurs "mobilier urbain" documentées sur le wiki OSM,
# candidates à un futur rendu si elles apparaissent dans Bxl.
# (liste indicative, à compléter si le wiki évolue ou si de nouveaux
# besoins de micro-mapping apparaissent — cf. issue #51)
WIKI_VALUES = {
    "amenity": ["bench", "lounger", "waste_basket", "vending_machine",
                "drinking_water", "clock", "bicycle_parking", "shelter",
                "give_box"],
    "barrier": ["bollard", "gate", "bus_trap", "cycle_barrier", "lift_gate",
                "planter", "kissing_gate", "block", "full-height_turnstile",
                "swing_gate", "stile"],
    "highway": ["street_lamp"],
}


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
                   help="export osmium élargi (rendus + candidats wiki)")
    p.add_argument("--config", default="map.config.yaml")
    p.add_argument("--report", default="street_furniture_report.md")
    args = p.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"✗  {cfg_path} introuvable", file=sys.stderr); sys.exit(1)
    config = yaml.safe_load(cfg_path.read_text())
    subtypes = (config.get("layers", {}).get("street_furniture", {})
                .get("subtypes") or {})

    configured_by_tag = {"amenity": set(), "barrier": set(), "highway": set()}
    has_entrance_subtype = False
    for val, scfg in subtypes.items():
        tag = (scfg or {}).get("tag")
        if tag in configured_by_tag:
            configured_by_tag[tag].add(val)
        elif tag == "entrance":
            has_entrance_subtype = True

    all_path = Path(args.all_json)
    if not all_path.exists():
        print(f"✗  {all_path} introuvable", file=sys.stderr); sys.exit(1)

    counts = {"amenity": {}, "barrier": {}, "highway": {}}
    vending_counts = {}
    entrance_count = 0

    for feat in load_features(all_path):
        props = feat.get("properties") or {}
        for tag in ("amenity", "barrier", "highway"):
            val = props.get(tag)
            candidates = set(WIKI_VALUES.get(tag, [])) | configured_by_tag[tag]
            if val and val in candidates:
                counts[tag][val] = counts[tag].get(val, 0) + 1
        if props.get("entrance"):
            entrance_count += 1
        v = props.get("vending")
        if v:
            vending_counts[v] = vending_counts.get(v, 0) + 1

    rendered, missing, no_data = [], [], []
    for tag in ("amenity", "barrier", "highway"):
        present = set(counts[tag])
        reference = present | configured_by_tag[tag] | set(WIKI_VALUES.get(tag, []))
        for val in sorted(reference):
            cnt = counts[tag].get(val, 0)
            is_cfg = val in configured_by_tag[tag]
            if cnt == 0:
                no_data.append((tag, val, is_cfg))
            elif is_cfg:
                rendered.append((tag, val, cnt))
            else:
                missing.append((tag, val, cnt))

    entrance_status = "rendu" if has_entrance_subtype else "NON CONFIGURÉ"
    lines = ["# Street furniture coverage report", "",
              "Comparaison entre les tags `amenity=*` / `barrier=*` / "
              "`highway=street_lamp` présents dans l'extrait Bruxelles et "
              "ceux rendus par `map.config.yaml` (cf. issue #51 — "
              "\"Streets furnitures, small object (micromapping)\").", "",
              f"- ✓ rendus : {len(rendered)}",
              f"- ⚠ manquants (présents mais sans style) : {len(missing)}",
              f"- · sans donnée dans le pbf Bxl : {len(no_data)}",
              f"- `entrance=*` (toutes valeurs confondues) : "
              f"{entrance_count} features — {entrance_status} "
              "(rendu uniforme par clé, pas par valeur)",
              ""]

    if missing:
        lines += ["## ⚠ Présents dans Bxl mais non rendus", "",
                  "Ces valeurs existent dans le pbf mais n'ont pas de "
                  "sous-type dans `layers.street_furniture.subtypes` → "
                  "ajouter un rendu dans `map.config.yaml` (et au besoin "
                  "une icône, voir `missing-icons.txt` après "
                  "`generate_poi_icons.py`).", "",
                  "| tag | valeur | features |", "| :--- | :--- | ---: |"]
        for tag, val, cnt in sorted(missing, key=lambda x: -x[2]):
            lines.append(f"| `{tag}` | `{val}` | {cnt} |")
        lines.append("")

    lines += ["## ✓ Rendus", "", "| tag | valeur | features |",
              "| :--- | :--- | ---: |"]
    for tag, val, cnt in sorted(rendered, key=lambda x: -x[2]):
        lines.append(f"| `{tag}` | `{val}` | {cnt} |")
    lines.append("")

    if no_data:
        lines += ["## · Sans donnée dans le pbf Bxl", "",
                  "Configurés et/ou listés comme candidats (wiki OSM), "
                  "mais absents de l'extrait actuel — aucun rendu généré "
                  "pour eux (conforme : on ne rend pas ce qui n'existe pas "
                  "dans les données).", "",
                  "| tag | valeur | configuré dans map.config.yaml ? |",
                  "| :--- | :--- | :---: |"]
        for tag, val, is_cfg in sorted(no_data):
            lines.append(f"| `{tag}` | `{val}` | {'oui' if is_cfg else 'non'} |")
        lines.append("")

    if vending_counts:
        lines += ["## Sous-types `vending=*` (raffinement d'icône)", "",
                  "`amenity=vending_machine` est déjà rendu ci-dessus ; ces "
                  "valeurs ne créent pas de couche supplémentaire, "
                  "seulement une icône plus précise si elle existe (même "
                  "principe que `cuisine=*` / `religion=*` pour les POI — "
                  "cf. `generate_poi_icons.py` et `missing-icons.txt`).", "",
                  "| vending | features |", "| :--- | ---: |"]
        for val, cnt in sorted(vending_counts.items(), key=lambda x: -x[1]):
            lines.append(f"| `{val}` | {cnt} |")
        lines.append("")

    Path(args.report).write_text("\n".join(lines) + "\n")

    print(f"✓  {args.report} : {len(rendered)} rendus, "
          f"{len(missing)} manquants, {len(no_data)} sans donnée, "
          f"{entrance_count} entrance, {len(vending_counts)} types vending")

    if missing:
        print("⚠  street furniture présents mais non rendus :",
              ", ".join(f"{t}={v}({c})" for t, v, c in
                        sorted(missing, key=lambda x: -x[2])))


if __name__ == "__main__":
    main()
