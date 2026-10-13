#!/usr/bin/env python3
import argparse, json, sys
from pathlib import Path

ZOOM_BLOCKS = [(z, z) for z in range(10, 19)]


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


def existing_range(feat):
    hint = feat.get("tippecanoe") or {}
    lo = hint.get("minzoom")
    hi = hint.get("maxzoom")
    return (lo if isinstance(lo, (int, float)) else float("-inf"),
            hi if isinstance(hi, (int, float)) else float("inf"))


def process(feat, rules):
    props = feat.get("properties") or {}
    lo, hi = existing_range(feat)
    segments = []

    for zmin, zmax in ZOOM_BLOCKS:
        if zmax < lo or zmin > hi:
            continue
        zmin, zmax = int(max(zmin, lo)), int(min(zmax, hi))
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

    merged = []
    a_zmin, a_zmax, a_keep = segments[0]
    for zmin, zmax, keep in segments[1:]:
        if keep == a_keep and zmin == a_zmax + 1:
            a_zmax = zmax
        else:
            merged.append((a_zmin, a_zmax, a_keep))
            a_zmin, a_zmax, a_keep = zmin, zmax, keep
    merged.append((a_zmin, a_zmax, a_keep))

    base_hint = dict(feat.get("tippecanoe") or {})
    out = []
    for zmin, zmax, keep in merged:
        hint = dict(base_hint)
        hint["minzoom"] = zmin
        hint["maxzoom"] = zmax
        f = {"type": "Feature", "geometry": feat.get("geometry"),
             "properties": filter_props(props, keep),
             "tippecanoe": hint}
        if feat.get("id") is not None:
            f["id"] = feat["id"]
        out.append(f)
    return out


def load_geojson(path):
    text = path.read_text()
    try:
        data = json.loads(text)
        if isinstance(data, dict) and data.get("type") == "Feature":
            return {"type": "FeatureCollection", "features": [data]}, True
        return data, False
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
    return {"type": "FeatureCollection", "features": feats}, True


def process_layer(name, rules, dry_run):
    return process_file(Path(f"{name}.json"), rules, dry_run)


def layer_jobs(name, cfg):
    files = cfg.get("files")
    if files:
        return [(f"{name} ({fname})", Path(fname), rules) for fname, rules in files.items()]
    return [(name, Path(f"{name}.json"), cfg.get("rules", []))]


def process_file(path, rules, dry_run):
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
            path.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in out))
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

        for label, path, rules in layer_jobs(name, cfg):
            print(f"→ {label}  ({len(rules)} règles)", end="  ")
            stats = process_file(path, rules, args.dry_run)

            if "error" in stats:
                print(f"✗  {stats['error']}")
                rows.append(f"| {label} | — | — | — | ✗ |")
                continue

            pct = round(100 * stats["out"] / stats["in"]) if stats["in"] else 0
            exp = f" +{stats['expanded']} splits" if stats["expanded"] else ""
            mark = "○" if args.dry_run else "✓"
            print(f"{mark}  {stats['in']} → {stats['out']}  "
                  f"({stats['dropped']} drop{exp})")

            total_in   += stats["in"]
            total_out  += stats["out"]
            total_drop += stats["dropped"]
            rows.append(f"| {label} | {stats['in']} | {stats['out']} "
                        f"| {stats['dropped']} | {pct}% |")

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
