import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import apply_granulometry
from build_map import ROAD_ORDER, config_hash

CONFIG = ROOT / "map.config.yaml"
EXTERNAL_STYLES = [ROOT / "www" / "style.json", ROOT / "www" / "bright-test.json"]
ZOOMS = [(z, z) for z in range(10, 19)]


def run(*args):
    result = subprocess.run([sys.executable, *map(str, args)], cwd=ROOT,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def build(config_path, out_dir, tag):
    style = out_dir / f"style_{tag}.json"
    gran = out_dir / f"gran_{tag}.json"
    params = out_dir / f"pmtiles_{tag}.json"
    run("build_map.py", "--config", config_path, "--style-out", style,
        "--gran-out", gran, "--pmtiles-out", params)
    return json.loads(style.read_text()), json.loads(gran.read_text())


def retro(style, out_dir, tag):
    style_path = out_dir / f"retro_in_{tag}.json"
    style_path.write_text(json.dumps(style, ensure_ascii=False))
    out = out_dir / f"config_{tag}.yaml"
    run("retro_style.py", "--style", style_path, "--out", out)
    return out


def load_yaml(path):
    return yaml.safe_load(Path(path).read_text())


def layers_by_id(style):
    return {l["id"]: l for l in style["layers"]}


def comparable(style):
    meta = dict(style.get("metadata") or {})
    meta.pop("brussels:config_hash", None)
    return {"layers": style["layers"], "sources": style["sources"],
            "glyphs": style.get("glyphs"), "metadata": meta}


def assert_same_style(a, b):
    la, lb = layers_by_id(a), layers_by_id(b)
    assert [l["id"] for l in a["layers"]] == [l["id"] for l in b["layers"]], \
        f"ordre/ids différents : manquants={sorted(set(la) - set(lb))} nouveaux={sorted(set(lb) - set(la))}"
    diff = [k for k in la if la[k] != lb[k]]
    assert not diff, f"layers modifiés par le round-trip : {diff}"
    assert comparable(a) == comparable(b)


def sample_features(layer_name, *configs):
    samples = [{}]
    for cfg in configs:
        st = ((cfg.get("layers") or {}).get(layer_name) or {}).get("subtypes") or {}
        for value, scfg in st.items():
            tag = (scfg or {}).get("tag") or layer_name
            samples.append({tag: value, "name": "x", "access": "private"})
    if layer_name == "roads":
        samples += [{"highway": v, "name": "x", "maxspeed": "30"} for v in ROAD_ORDER]
        samples += [{"man_made": "bridge"}, {"man_made": "tunnel"}, {"highway": "crossing"}]
    return samples


def effective(gran, layer_name, samples):
    if layer_name not in gran["layers"]:
        return [[(10, 18, sorted(props))] for props in samples]
    rules = gran["layers"][layer_name].get("rules", [])
    out = []
    for props in samples:
        feats = apply_granulometry.process({"type": "Feature", "geometry": None,
                                            "properties": dict(props)}, rules)
        out.append([(f["tippecanoe"]["minzoom"], f["tippecanoe"]["maxzoom"],
                     sorted(f["properties"])) for f in feats])
    return out


@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("idempotence")
    original = load_yaml(CONFIG)
    s1, g1 = build(CONFIG, tmp, "1")
    y1 = retro(s1, tmp, "1")
    s2, g2 = build(y1, tmp, "2")
    y2 = retro(s2, tmp, "2")
    s3, g3 = build(y2, tmp, "3")
    return {"original": original, "s1": s1, "g1": g1, "y1": load_yaml(y1),
            "s2": s2, "g2": g2, "y2": load_yaml(y2), "s3": s3, "g3": g3}


@pytest.fixture(autouse=True)
def zoom_blocks(monkeypatch):
    monkeypatch.setattr(apply_granulometry, "ZOOM_BLOCKS", ZOOMS)


def test_style_fixpoint_after_retro(chain):
    assert_same_style(chain["s1"], chain["s2"])


def test_style_stable_on_second_cycle(chain):
    assert_same_style(chain["s2"], chain["s3"])


def test_yaml_fixpoint(chain):
    assert chain["y1"] == chain["y2"]


def test_granulometry_equivalent_after_retro(chain):
    for name in chain["original"]["layers"]:
        samples = sample_features(name, chain["original"], chain["y1"])
        assert effective(chain["g1"], name, samples) == effective(chain["g2"], name, samples), name


def test_no_subtype_lost(chain):
    lost = []
    for name, layer in chain["original"]["layers"].items():
        before = set(((layer or {}).get("subtypes") or {}))
        after = set(((chain["y1"]["layers"].get(name) or {}).get("subtypes") or {}))
        lost += [f"{name}.{k}" for k in sorted(before - after)]
    assert not lost, f"sous-types perdus par retro_style.py : {lost}"


def test_road_settings_preserved(chain):
    orig = chain["original"]["layers"]["roads"]["subtypes"]
    back = chain["y1"]["layers"]["roads"]["subtypes"]
    for value, scfg in orig.items():
        for field in ("color", "outline_color", "appear_at"):
            if field in scfg:
                assert back[value].get(field) == scfg[field], f"roads.{value}.{field}"


def test_labels_do_not_change_appear_at(chain):
    back = chain["y1"]["layers"]["roads"]["subtypes"]
    labels_at = chain["original"]["layers"]["roads"]["labels_at"]
    for value in ("primary", "secondary", "tertiary", "residential"):
        assert back[value]["appear_at"] < labels_at, value


def test_style_metadata(chain):
    meta = chain["s1"]["metadata"]
    assert meta["brussels:config_hash"] == config_hash(chain["original"])
    assert meta["brussels:map"].get("version") == chain["original"]["map"].get("version")
    assert chain["y1"]["map"].get("version") == chain["original"]["map"].get("version")


def test_config_hash_ignores_key_order():
    a = {"map": {"name": "A", "zoom": 13}, "layers": {"x": {"color": "#fff"}}}
    b = {"layers": {"x": {"color": "#fff"}}, "map": {"zoom": 13, "name": "A"}}
    assert config_hash(a) == config_hash(b)
    assert config_hash(a) != config_hash({**a, "map": {"name": "B", "zoom": 13}})


@pytest.mark.parametrize("style_path", EXTERNAL_STYLES, ids=lambda p: p.name)
def test_external_style_converges_after_one_pass(style_path, tmp_path):
    if not style_path.exists():
        pytest.skip(f"{style_path} absent")
    y1 = retro(json.loads(style_path.read_text()), tmp_path, "a")
    s1, g1 = build(y1, tmp_path, "a")
    y2 = retro(s1, tmp_path, "b")
    s2, g2 = build(y2, tmp_path, "b")
    y3 = retro(s2, tmp_path, "c")
    assert_same_style(s1, s2)
    assert load_yaml(y2) == load_yaml(y3)
    for name in load_yaml(y2)["layers"]:
        samples = sample_features(name, load_yaml(y1), load_yaml(y2))
        assert effective(g1, name, samples) == effective(g2, name, samples), name
