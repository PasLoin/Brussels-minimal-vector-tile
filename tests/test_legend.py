import copy
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from build_map import LEGEND_FALLBACK_COLOR, SWATCH_TYPES, build_style, paint_color

CONFIG = yaml.safe_load((ROOT / "map.config.yaml").read_text())


def legend_of(config):
    return build_style(config)["metadata"]["brussels:legend"]


def group(legend, gid):
    return next(g for g in legend if g["id"] == gid)


def ids_of(g):
    return g["layers"] + [i for it in g["items"] for i in it["layers"]]


def test_every_sourced_layer_is_in_exactly_one_entry():
    style = build_style(CONFIG)
    seen = [i for g in style["metadata"]["brussels:legend"] for i in ids_of(g)]
    sourced = [l["id"] for l in style["layers"] if l.get("source")]
    assert sorted(seen) == sorted(sourced)


def test_group_order_follows_config():
    assert [g["id"] for g in legend_of(CONFIG)] == list(CONFIG["layers"])


def test_item_order_follows_config():
    order = list(CONFIG["layers"]["roads"]["subtypes"])
    assert [i["id"] for i in group(legend_of(CONFIG), "roads")["items"]] == order


def test_late_features_are_listed():
    legend = legend_of(CONFIG)
    assert group(legend, "leisure")["layers"]
    assert "pitch" in [i["id"] for i in group(legend, "leisure")["items"]]
    assert "river" in [i["id"] for i in group(legend, "water")["items"]]
    assert "man_made-bridge-fill" in group(legend, "roads")["layers"]


def test_shared_layers_stay_at_group_level():
    legend = legend_of(CONFIG)
    assert "railway-bridge-casing" in group(legend, "railway")["layers"]
    assert "road-labels" in group(legend, "roads")["layers"]


def test_aliases_attach_layers_to_subtypes():
    legend = legend_of(CONFIG)
    ped = {i["id"]: i["layers"] for i in group(legend, "pedestrian")["items"]}
    assert "pedestrian-street-fill" in ped["pedestrian"]
    trees = {i["id"]: i["layers"] for i in group(legend, "trees")["items"]}
    assert "trees-row-line" in trees["tree_row"]


def test_colors_come_from_config():
    legend = legend_of(CONFIG)
    assert group(legend, "water")["color"] == CONFIG["layers"]["water"]["color"]
    rail = next(i for i in group(legend, "railway")["items"] if i["id"] == "rail")
    assert rail["color"] == CONFIG["layers"]["railway"]["subtypes"]["rail"]["color"]


def test_color_falls_back_to_paint_then_default():
    cfg = copy.deepcopy(CONFIG)
    cfg["layers"]["boundaries"].pop("color")
    g = group(legend_of(cfg), "boundaries")
    assert g["color"] == paint_color([{"id": "boundaries", "paint": {"line-color": "#ac46ac"}}])
    assert paint_color([{"id": "x", "type": "symbol", "paint": {}}]) is None
    assert LEGEND_FALLBACK_COLOR.startswith("#")


def test_roads_without_group_color_use_first_item():
    g = group(legend_of(CONFIG), "roads")
    assert g["color"] == g["items"][0]["color"]


def test_subtype_label_override():
    cfg = copy.deepcopy(CONFIG)
    cfg["layers"]["railway"]["subtypes"]["tram"]["label"] = "Tramway"
    tram = next(i for i in group(legend_of(cfg), "railway")["items"] if i["id"] == "tram")
    assert tram["label"] == "Tramway"


def test_swatch_override_and_default():
    legend = legend_of(CONFIG)
    assert group(legend, "water")["swatch"] == "fill"
    assert group(legend, "roads")["swatch"] == "line"
    assert all(g["swatch"] in SWATCH_TYPES for g in legend)
    cfg = copy.deepcopy(CONFIG)
    cfg["layers"]["water"]["swatch"] = "nimporte"
    assert group(legend_of(cfg), "water")["swatch"] == "line"


def test_visible_flag():
    cfg = copy.deepcopy(CONFIG)
    cfg["layers"]["boundaries"]["visible"] = False
    assert group(legend_of(cfg), "boundaries")["visible"] is False
    assert group(legend_of(CONFIG), "boundaries")["visible"] is True


def test_retro_preserves_custom_legend(tmp_path):
    cfg = copy.deepcopy(CONFIG)
    cfg["layers"]["railway"]["subtypes"]["tram"]["label"] = "Tramway"
    cfg["layers"]["railway"]["label"] = "Rail et tram"
    cfg["layers"]["boundaries"]["visible"] = False
    style = build_style(cfg)
    src = tmp_path / "style.json"
    src.write_text(json.dumps(style, ensure_ascii=False))
    out = tmp_path / "config.yaml"
    subprocess.run([sys.executable, "retro_style.py", "--style", str(src), "--out", str(out)],
                   cwd=ROOT, check=True, capture_output=True)
    back = build_style(yaml.safe_load(out.read_text()))
    assert back["metadata"]["brussels:legend"] == style["metadata"]["brussels:legend"]


def test_every_configured_subtype_is_listed():
    legend = {g["id"]: g for g in legend_of(CONFIG)}
    missing = {name: [k for k in (layer.get("subtypes") or {})
                      if k not in [i["id"] for i in legend[name]["items"]]]
               for name, layer in CONFIG["layers"].items() if name in legend}
    assert {k: v for k, v in missing.items() if v} == {}


def test_shared_layer_subtypes_are_filters():
    furniture = group(legend_of(CONFIG), "street_furniture")
    bench = next(i for i in furniture["items"] if i["id"] == "bench")
    assert bench["layers"] == []
    assert bench["filter"] == ["==", ["get", "amenity"], "bench"]
    entrance = next(i for i in furniture["items"] if i["id"] == "entrance")
    assert entrance["filter"] == ["has", "entrance"]
    playground = next(i for i in group(legend_of(CONFIG), "leisure")["items"] if i["id"] == "playground")
    assert playground["filter"] == ["==", ["get", "leisure"], "playground"]


def test_groups_without_shared_layers_have_no_filters():
    for gid in ("landuse", "trees", "pedestrian"):
        assert all("filter" not in i for i in group(legend_of(CONFIG), gid)["items"]), gid
