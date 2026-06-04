#!/usr/bin/env python3
"""
apply_granulometry.py
─────────────────────
Lit granulometry.json (généré par build_map.py) et filtre les fichiers
GeoJSON en ajoutant des hints tippecanoe par feature (minzoom/maxzoom).

Usage :
  python3 apply_granulometry.py                      # tous les layers
  python3 apply_granulometry.py --layers roads,poi   # layers spécifiques
  python3 apply_granulometry.py --dry-run            # rapport sans écriture
  python3 apply_granulometry.py --gran granulometry.json
"""

import argparse, json, sys
from pathlib import Path

ZOOM_BLOCKS = [(10,12),(13,14),(15,16),(17,18)]


def match_rule(rule, props):
    spec = rule.get("match")
    if not spec:
        return True
    for tag, allowed in spec.items():
        v = props.get(tag)
        if v is None:
            return False
        if allowed != ["*"] and str(v) not in [str(a) for a in allowed]:
            return False
    return True


def apply(rule, props):
    action = rule.get("action", "keep")
    kp     = rule.get("keep_properties", "ALL")
    if kp == "ALL":
        return action, None
    return action, list(kp)


def filter_props(props, keep):
    if keep is None: return dict(props)
    return {k: v for k, v in props.items() if k in keep}


def process(feat, rules):
    props = feat.get("properties") or {}
    segments = []

    for zmin, zmax in ZOOM_BLOCKS:
        for rule in rules:
            rmin = rule.get("zoom_min", 10)
            rmax = rule.get("zoom_max", 18)
            if rmax < zmin or rmin > zmax:
                continue
            if not match_rule(rule, props):
                continue
            action, keep = apply(rule, props)
            if action != "drop":
                segments.append((zmin, zmax, keep))
            break

    if not segments:
        return []

    # Fusionner les blocs consécutifs avec le même keep
    merged = []
    a_zmin, a_zmax, a_keep = segments[0]
    for zmin, zmax, keep in segments[1:]:
        if keep == a_keep:
            a_zmax = zmax
        else:
            merged.append((a_zmin, a_zmax, a_keep))
            a_zmin, a_zmax, a_keep = zmin, zmax, keep
    merged.append((a_zmin, a_zmax, a_keep))

    out = []
    for zmin, zmax, keep in merged:
        f = {"type": "Feature", "geometry": feat.get("geometry"),
             "properties": filter_props(props, keep),
             "tippecanoe": {"minzoom": zmin, "maxzoom": zmax}}
        if feat.get("id") is not None:
            f["id"] = feat["id"]
        out.append(f)
    return out


def load_geojson(path):
    """
    Charge un fichier GeoJSON en gérant deux formats :
      - FeatureCollection standard  {"type":"FeatureCollection","features":[...]}
      - Newline-delimited JSON       une Feature JSON par ligne (format extract_stib_routes.py)
    Retourne (data, is_ndjson).
    """
    text = path.read_text()
    # Tenter le parsing standard d'abord
    try:
        data = json.loads(text)
        return data, False
    except json.JSONDecodeError:
        pass
    # Fallback : NDJSON — une feature par ligne non vide
    feats = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            feats.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return {"type": "FeatureCollection", "features": feats}, True


def process_layer(name, rules, dry_run):
    path = Path(f"{name}.json")
    if not path.exists():
        return {"error": f"{path} introuvable"}

    data, was_ndjson = load_geojson(path)
    feats = data.get("features", [])
    out, dropped, expanded = [], 0, 0

    for f in feats:
        r = process(f, rules)
        if not r:
            dropped += 1
        else:
            expanded += max(0, len(r) - 1)
            out.extend(r)

    if not dry_run:
        data["features"] = out
        if was_ndjson:
            # Réécrire en NDJSON pour rester compatible avec tippecanoe
            path.write_text(
                "\n".join(json.dumps(f, ensure_ascii=False) for f in out) + "\n"
            )
        else:
            path.write_text(json.dumps(data, ensure_ascii=False))

    return {"in": len(feats), "out": len(out),
            "dropped": dropped, "expanded": expanded}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--gran",    default="granulometry.json")
    p.add_argument("--layers",  default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--report",  default="granulometry_report.md")
    args = p.parse_args()

    gran_path = Path(args.gran)
    if not gran_path.exists():
        print(f"✗  {gran_path} introuvable — lance d'abord build_map.py", file=sys.stderr)
        sys.exit(1)

    gran = json.loads(gran_path.read_text())
    layer_cfgs = gran.get("layers", {})

    targets = ([l.strip() for l in args.layers.split(",")]
               if args.layers else list(layer_cfgs.keys()))

    if args.dry_run:
        print("  (dry-run — aucun fichier modifié)")

    rows = []
    total_in = total_out = total_drop = 0

    for name in targets:
        cfg = layer_cfgs.get(name)
        if not cfg:
            print(f"  ⚠  {name} absent de {gran_path}")
            continue

        rules = cfg.get("rules", [])
        print(f"→ {name}  ({len(rules)} règles)", end="  ")
        stats = process_layer(name, rules, args.dry_run)

        if "error" in stats:
            print(f"✗  {stats['error']}")
            rows.append(f"| {name} | — | — | ✗ |")
            continue

        pct = round(100 * stats["out"] / stats["in"]) if stats["in"] else 0
        exp = f" +{stats['expanded']} splits" if stats["expanded"] else ""
        mark = "○" if args.dry_run else "✓"
        print(f"{mark}  {stats['in']} → {stats['out']}  "
              f"({stats['dropped']} drop{exp})")

        total_in   += stats["in"]
        total_out  += stats["out"]
        total_drop += stats["dropped"]
        rows.append(f"| {name} | {stats['in']} | {stats['out']} "
                    f"| {stats['dropped']} | {pct}% |")

    # Rapport Markdown
    pct_total = round(100 * total_out / total_in) if total_in else 0
    report = ["# Granulometry report", "",
              f"Config: `{args.gran}`",
              f"Dry-run: {'oui' if args.dry_run else 'non'}", "",
              "| Layer | In | Out | Drop | % kept |",
              "| :--- | ---: | ---: | ---: | ---: |"] + rows + [
              f"| **Total** | **{total_in}** | **{total_out}** "
              f"| **{total_drop}** | **{pct_total}%** |"]
    Path(args.report).write_text("\n".join(report) + "\n")
    print(f"\n✓  rapport → {args.report}")
    print(f"✓  {total_in} → {total_out} features  "
          f"({pct_total}% conservés, {total_drop} supprimés)")

if __name__ == "__main__":
    main()
