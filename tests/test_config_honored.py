import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from build_map import build_granulometry, build_pmtiles_params, build_style

CONFIG = yaml.safe_load((ROOT / "map.config.yaml").read_text())
PROBE_COLOR = "#123456"
PROBE_OPACITY = 0.37


def style_of(config):
    return build_style(config)


def layers(style):
    return {l["id"]: l for l in style["layers"]}


def mutated(path, value):
    cfg = copy.deepcopy(CONFIG)
    node = cfg
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return cfg


def subtype_fields(field):
    out = []
    for name, layer in CONFIG["layers"].items():
        for value, scfg in ((layer or {}).get("subtypes") or {}).items():
            if field in (scfg or {}):
                out.append((name, value))
    return out


@pytest.mark.parametrize("name,value", subtype_fields("color"), ids=lambda x: str(x))
def test_every_subtype_color_is_used(name, value):
    cfg = mutated(["layers", name, "subtypes", value, "color"], PROBE_COLOR)
    assert PROBE_COLOR in json.dumps(style_of(cfg)), f"{name}.{value}.color ignoré"


@pytest.mark.parametrize("name,value", subtype_fields("outline_color"), ids=lambda x: str(x))
def test_every_subtype_outline_color_is_used(name, value):
    cfg = mutated(["layers", name, "subtypes", value, "outline_color"], PROBE_COLOR)
    assert PROBE_COLOR in json.dumps(style_of(cfg)), f"{name}.{value}.outline_color ignoré"


@pytest.mark.parametrize("name,value", subtype_fields("opacity"), ids=lambda x: str(x))
def test_every_subtype_opacity_is_used(name, value):
    cfg = mutated(["layers", name, "subtypes", value, "opacity"], PROBE_OPACITY)
    assert str(PROBE_OPACITY) in json.dumps(style_of(cfg)), f"{name}.{value}.opacity ignoré"


@pytest.mark.parametrize("name,value", subtype_fields("tunnel_color"), ids=lambda x: str(x))
def test_every_subtype_tunnel_color_is_used(name, value):
    cfg = mutated(["layers", name, "subtypes", value, "tunnel_color"], PROBE_COLOR)
    assert PROBE_COLOR in json.dumps(style_of(cfg)), f"{name}.{value}.tunnel_color ignoré"


@pytest.mark.parametrize("name,value", subtype_fields("appear_at"), ids=lambda x: str(x))
def test_every_subtype_appear_at_is_used(name, value):
    current = CONFIG["layers"][name]["subtypes"][value]["appear_at"]
    probe = 16 if current != 16 else 15
    cfg = mutated(["layers", name, "subtypes", value, "appear_at"], probe)
    before = json.dumps(style_of(CONFIG)) + json.dumps(build_granulometry(CONFIG))
    after = json.dumps(style_of(cfg)) + json.dumps(build_granulometry(cfg))
    assert before != after, f"{name}.{value}.appear_at ignoré"


def test_tree_leaf_colors_follow_config():
    tree = layers(style_of(CONFIG))["trees-tree"]
    by_color = CONFIG["layers"]["trees"]["subtypes"]["tree"]["by_color"]
    expr = json.dumps(tree["paint"]["text-color"])
    for col in by_color.values():
        assert col in expr


def test_railway_opacity_applies_to_surface_only():
    cfg = mutated(["layers", "railway", "subtypes", "tram", "opacity"], PROBE_OPACITY)
    ls = layers(style_of(cfg))
    assert ls["railway-tram"]["paint"]["line-opacity"] == PROBE_OPACITY
    assert ls["railway-tunnel-tram"]["paint"]["line-opacity"] != PROBE_OPACITY


def test_railway_tunnel_color_defaults_to_lightened_color():
    cfg = copy.deepcopy(CONFIG)
    del cfg["layers"]["railway"]["subtypes"]["subway"]["tunnel_color"]
    ls = layers(style_of(cfg))
    assert ls["railway-tunnel-subway"]["paint"]["line-color"] == "#cccccc"


def test_green_meadow_wood_grassland_have_own_layers():
    ls = layers(style_of(CONFIG))
    assert ls["green-meadow"]["filter"] == ["==", ["get", "landuse"], "meadow"]
    assert ls["green-wood"]["filter"] == ["==", ["get", "natural"], "wood"]
    assert ls["green-grassland"]["filter"] == ["==", ["get", "natural"], "grassland"]
    assert ls["green-forest"]["filter"] == ["==", ["get", "landuse"], "forest"]


def test_cemetery_matches_osm_carto():
    ls = layers(style_of(CONFIG))
    assert ls["landuse-cemetery"]["paint"] == {"fill-color": "#aacbaf"}
    hatch = ls["landuse-cemetery-hatch"]
    assert hatch["minzoom"] == 13
    assert hatch["paint"]["fill-pattern"] == [
        "match", ["get", "religion"],
        "christian", "grave_yard_christian",
        "jewish", "grave_yard_jewish",
        "muslim", "grave_yard_muslim",
        "grave_yard_generic"]


def test_pattern_metadata_lists_used_patterns_with_existing_files():
    patterns = style_of(CONFIG)["metadata"]["brussels:patterns"]
    assert {"military-hatch", "green-hatch", "grave_yard_generic",
            "grave_yard_christian", "grave_yard_jewish", "grave_yard_muslim"} <= set(patterns)
    for name, cfg in patterns.items():
        assert (ROOT / "www" / cfg["file"]).exists(), name


def test_unused_patterns_are_not_published():
    cfg = copy.deepcopy(CONFIG)
    cfg["patterns"]["inutile"] = {"file": "assets/x.svg"}
    assert "inutile" not in style_of(cfg)["metadata"]["brussels:patterns"]


def test_pitch_layers_generated_from_config_in_right_place():
    ids = [l["id"] for l in style_of(CONFIG)["layers"]]
    assert ids.index("leisure-outline") + 1 == ids.index("pitch-sport-fill")
    assert ids.index("pitch-sport-fill") + 1 == ids.index("pitch-sport-outline")
    assert ids.index("pitch-markings") + 1 == ids.index("poi-circle")
    cfg = mutated(["layers", "leisure", "sports", "values", "soccer", "color"], PROBE_COLOR)
    assert PROBE_COLOR in json.dumps(layers(style_of(cfg))["pitch-sport-fill"])


def test_no_pitch_layers_without_sports():
    cfg = copy.deepcopy(CONFIG)
    del cfg["layers"]["leisure"]["sports"]
    ids = [l["id"] for l in style_of(cfg)["layers"]]
    assert not [i for i in ids if i.startswith("pitch-")]


def test_buildings_tiles_follow_appear_at():
    params = build_pmtiles_params(CONFIG)["layers"]["buildings"]
    assert [i["file"] for i in params["inputs"]] == ["buildings_detail.json"]
    assert params["min_zoom"] == CONFIG["layers"]["buildings"]["appear_at"]
    cfg = mutated(["layers", "buildings", "appear_at"], 10)
    params = build_pmtiles_params(cfg)["layers"]["buildings"]
    assert params["inputs"] == [
        {"file": "buildings_merged.json", "min_zoom": 10, "max_zoom": 12},
        {"file": "buildings_detail.json", "min_zoom": 13, "max_zoom": 18}]


def test_buildings_granulometry_targets_tile_inputs():
    cfg = mutated(["layers", "buildings", "appear_at"], 10)
    files = build_granulometry(cfg)["layers"]["buildings"]["files"]
    assert files["buildings_merged.json"] == [{"zoom_min": 10, "zoom_max": 12, "keep_properties": "ALL"}]
    assert files["buildings_detail.json"] == [{"zoom_min": 13, "zoom_max": 18, "keep_properties": "ALL"}]


def test_tiles_override_from_config():
    cfg = mutated(["layers", "poi", "tiles"], {"max_zoom": 17, "simplification": 4})
    poi = build_pmtiles_params(cfg)["layers"]["poi"]
    assert (poi["max_zoom"], poi["simplification"]) == (17, 4)
    assert style_of(cfg)["metadata"]["brussels:tiles"] == {"poi": {"max_zoom": 17, "simplification": 4}}


def test_generate_pmtiles_reads_params(tmp_path):
    params = tmp_path / "p.json"
    params.write_text(json.dumps(build_pmtiles_params(CONFIG)))
    script = ('source <(sed -n "/^param() {/,/^}/p" generate_pmtiles.bash); '
              f'PARAMS="{params}"; param layers; param settings poi; param inputs buildings')
    out = subprocess.run(["bash", "-c", script], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout.splitlines()
    assert "buildings" in out and "building_parts" in out
    assert "10 16 10" in out
    assert "buildings_detail.json\t13\t18" in out


@pytest.mark.parametrize("name", [n for n, l in CONFIG["layers"].items()
                                  if "color" in (l or {}) and (l or {}).get("subtypes")])
def test_layer_color_is_fallback_for_subtypes(name):
    cfg = copy.deepcopy(CONFIG)
    cfg["layers"][name]["color"] = PROBE_COLOR
    for scfg in cfg["layers"][name]["subtypes"].values():
        (scfg or {}).pop("color", None)
    assert PROBE_COLOR in json.dumps(style_of(cfg)), f"{name}.color ignoré"


def test_roads_have_no_layer_color():
    assert "color" not in CONFIG["layers"]["roads"]
    assert "border_color" not in CONFIG["layers"]["roads"]
