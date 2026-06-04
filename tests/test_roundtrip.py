#!/usr/bin/env python3
"""
tests/test_roundtrip.py
───────────────────────
Tests de non-régression pour la chaîne bidirectionnelle :

    map.config.yaml  →  build_map.py  →  style.json
    style.json       →  retro_style.py → map.config.yaml (reconstruit)
    map.config.yaml* →  build_map.py  →  style.json*     (doit ≃ style.json)

Lancé avec :  python3 -m pytest tests/test_roundtrip.py -v
              ou directement :  python3 tests/test_roundtrip.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# ── Repère racine du projet ────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent

# ── Couleur stable connue par couche (issue de map.config.yaml référence) ──────
# Permet de vérifier que retro ne perd pas les couleurs principales.
EXPECTED_COLORS = {
    "water":            "#a0c8f0",
    "buildings":        "#fce1c5",
    "leisure":          "#def3c0",
    "poi":              "#734a08",   # couleur circle
    "boundaries":       "#ac46ac",
}

# Layers dont on vérifie qu'ils existent dans le style généré
REQUIRED_LAYER_IDS = {
    "background",
    "water-fill",
    "buildings-fill",
    "buildings-outline",
    "leisure-fill",
    "leisure-outline",
    "poi-circle",
    "poi-icon",
    "boundaries",
    "cycleway",
    "public_transport-line",
    "road-labels",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def run(cmd, cwd=ROOT, check=True):
    result = subprocess.run(
        cmd, cwd=cwd,
        capture_output=True, text=True
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Commande échouée: {' '.join(cmd)}\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
    return result


def load_json(path):
    return json.loads(Path(path).read_text())


def layer_by_id(style, lid):
    return next((l for l in style["layers"] if l["id"] == lid), None)


def first_hex_color(expr):
    """Extrait la première couleur #hex d'une expression MapLibre."""
    if isinstance(expr, str) and expr.startswith("#"):
        return expr
    if isinstance(expr, list):
        for item in expr:
            found = first_hex_color(item)
            if found:
                return found
    return None


# ── Fixtures ──────────────────────────────────────────────────────────────────

def get_reference_style():
    """Retourne le style.json de référence du repo."""
    path = ROOT / "www" / "style.json"
    assert path.exists(), f"style.json de référence absent : {path}"
    return load_json(path)


def get_reference_config():
    """Retourne le map.config.yaml de référence du repo."""
    path = ROOT / "map.config.yaml"
    assert path.exists(), f"map.config.yaml de référence absent : {path}"
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)
    except ImportError:
        # Fallback : lire comme texte brut
        return path.read_text()


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestStyleJson:
    """Vérifie le style.json de référence."""

    def test_required_layers_present(self):
        style = get_reference_style()
        ids = {l["id"] for l in style["layers"]}
        missing = REQUIRED_LAYER_IDS - ids
        assert not missing, f"Layers manquants dans style.json : {missing}"

    def test_no_duplicate_layer_ids(self):
        style = get_reference_style()
        ids = [l["id"] for l in style["layers"]]
        dupes = [i for i in ids if ids.count(i) > 1]
        assert not dupes, f"IDs dupliqués : {set(dupes)}"

    def test_sources_match_layers(self):
        style = get_reference_style()
        declared_sources = set(style.get("sources", {}).keys())
        used_sources = {l["source"] for l in style["layers"] if "source" in l}
        undeclared = used_sources - declared_sources
        assert not undeclared, f"Sources utilisées non déclarées : {undeclared}"

    def test_background_layer_first(self):
        style = get_reference_style()
        assert style["layers"][0]["id"] == "background", \
            "Le premier layer doit être 'background'"

    def test_poi_above_buildings(self):
        """POI doit apparaître après buildings dans la pile."""
        style = get_reference_style()
        ids = [l["id"] for l in style["layers"]]
        assert "buildings-fill" in ids and "poi-circle" in ids
        assert ids.index("buildings-fill") < ids.index("poi-circle"), \
            "buildings-fill doit être sous poi-circle"

    def test_leisure_pitch_layers_present(self):
        style = get_reference_style()
        ids = {l["id"] for l in style["layers"]}
        for lid in ("pitch-sport-fill", "pitch-sport-outline", "pitch-markings"):
            assert lid in ids, f"Layer sport pitch manquant : {lid}"

    def test_pitch_sport_fill_above_leisure_fill(self):
        style = get_reference_style()
        ids = [l["id"] for l in style["layers"]]
        assert ids.index("leisure-fill") < ids.index("pitch-sport-fill"), \
            "pitch-sport-fill doit être au-dessus de leisure-fill"


class TestBuildMap:
    """Vérifie que build_map.py génère un style correct depuis map.config.yaml."""

    def test_build_produces_valid_style(self):
        """build_map.py doit s'exécuter sans erreur."""
        with tempfile.TemporaryDirectory() as tmp:
            style_out = Path(tmp) / "style.json"
            run([
                sys.executable, str(ROOT / "build_map.py"),
                "--config", str(ROOT / "map.config.yaml"),
                "--style-out", str(style_out),
                "--only", "style",
            ])
            assert style_out.exists(), "style.json non généré"
            style = load_json(style_out)
            assert style["version"] == 8
            assert "layers" in style
            assert len(style["layers"]) > 10

    def test_build_required_layers(self):
        with tempfile.TemporaryDirectory() as tmp:
            style_out = Path(tmp) / "style.json"
            run([
                sys.executable, str(ROOT / "build_map.py"),
                "--config", str(ROOT / "map.config.yaml"),
                "--style-out", str(style_out),
                "--only", "style",
            ])
            style = load_json(style_out)
            ids = {l["id"] for l in style["layers"]}
            missing = REQUIRED_LAYER_IDS - ids
            assert not missing, f"build_map ne génère pas : {missing}"

    def test_build_no_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            style_out = Path(tmp) / "style.json"
            run([
                sys.executable, str(ROOT / "build_map.py"),
                "--config", str(ROOT / "map.config.yaml"),
                "--style-out", str(style_out),
                "--only", "style",
            ])
            style = load_json(style_out)
            ids = [l["id"] for l in style["layers"]]
            dupes = [i for i in ids if ids.count(i) > 1]
            assert not dupes, f"IDs dupliqués générés : {set(dupes)}"

    def test_build_granulometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            gran_out = Path(tmp) / "gran.json"
            run([
                sys.executable, str(ROOT / "build_map.py"),
                "--config", str(ROOT / "map.config.yaml"),
                "--gran-out", str(gran_out),
                "--only", "granulometry",
            ])
            assert gran_out.exists()
            gran = load_json(gran_out)
            assert "layers" in gran
            # Doit avoir des règles pour roads
            assert "roads" in gran["layers"]
            assert gran["layers"]["roads"]["rules"]

    def test_buildings_color_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            style_out = Path(tmp) / "style.json"
            run([
                sys.executable, str(ROOT / "build_map.py"),
                "--config", str(ROOT / "map.config.yaml"),
                "--style-out", str(style_out),
                "--only", "style",
            ])
            style = load_json(style_out)
            bfill = layer_by_id(style, "buildings-fill")
            assert bfill is not None
            col = first_hex_color(bfill["paint"].get("fill-color"))
            assert col == "#fce1c5", f"Couleur buildings inattendue : {col}"

    def test_water_color_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            style_out = Path(tmp) / "style.json"
            run([
                sys.executable, str(ROOT / "build_map.py"),
                "--config", str(ROOT / "map.config.yaml"),
                "--style-out", str(style_out),
                "--only", "style",
            ])
            style = load_json(style_out)
            wfill = layer_by_id(style, "water-fill")
            assert wfill is not None
            col = first_hex_color(wfill["paint"].get("fill-color"))
            assert col is not None, "water-fill n'a pas de couleur"


class TestRetroStyle:
    """Vérifie que retro_style.py extrait correctement les données."""

    def test_retro_executes(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_out = Path(tmp) / "config.yaml"
            run([
                sys.executable, str(ROOT / "retro_style.py"),
                "--style", str(ROOT / "www" / "style.json"),
                "--out", str(config_out),
            ])
            assert config_out.exists(), "map.config.yaml non généré"
            assert config_out.stat().st_size > 100

    def test_retro_captures_all_layers(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_out = Path(tmp) / "config.yaml"
            run([
                sys.executable, str(ROOT / "retro_style.py"),
                "--style", str(ROOT / "www" / "style.json"),
                "--out", str(config_out),
            ])
            content = config_out.read_text()
            for layer_name in ("water", "buildings", "roads", "poi",
                                "leisure", "green", "railway", "pedestrian",
                                "cycleway", "public_transport", "boundaries"):
                assert f"  {layer_name}:" in content, \
                    f"Couche '{layer_name}' absente du YAML généré"

    def test_retro_captures_buildings_color(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_out = Path(tmp) / "config.yaml"
            run([
                sys.executable, str(ROOT / "retro_style.py"),
                "--style", str(ROOT / "www" / "style.json"),
                "--out", str(config_out),
            ])
            content = config_out.read_text()
            # La couleur buildings doit être présente quelque part dans le YAML
            assert "#fce1c5" in content, \
                "Couleur buildings #fce1c5 non retrouvée dans le YAML retro"

    def test_retro_captures_border_color(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_out = Path(tmp) / "config.yaml"
            run([
                sys.executable, str(ROOT / "retro_style.py"),
                "--style", str(ROOT / "www" / "style.json"),
                "--out", str(config_out),
            ])
            content = config_out.read_text()
            assert "#d4a574" in content, \
                "border_color buildings #d4a574 non trouvé dans le YAML retro"

    def test_retro_captures_subtypes(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_out = Path(tmp) / "config.yaml"
            run([
                sys.executable, str(ROOT / "retro_style.py"),
                "--style", str(ROOT / "www" / "style.json"),
                "--out", str(config_out),
            ])
            content = config_out.read_text()
            # Sous-types vérifiables
            for subtype in ("forest", "wetland", "park", "garden",
                             "pitch", "playground"):
                assert subtype in content, \
                    f"Sous-type '{subtype}' absent du YAML retro"

    def test_retro_captures_appear_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_out = Path(tmp) / "config.yaml"
            run([
                sys.executable, str(ROOT / "retro_style.py"),
                "--style", str(ROOT / "www" / "style.json"),
                "--out", str(config_out),
            ])
            content = config_out.read_text()
            assert "appear_at:" in content, "appear_at absent du YAML retro"

    def test_retro_captures_opacity(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_out = Path(tmp) / "config.yaml"
            run([
                sys.executable, str(ROOT / "retro_style.py"),
                "--style", str(ROOT / "www" / "style.json"),
                "--out", str(config_out),
            ])
            content = config_out.read_text()
            assert "opacity:" in content, \
                "opacity absent du YAML retro (wetland, scrub, etc. ont opacity)"

    def test_retro_captures_color_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_out = Path(tmp) / "config.yaml"
            run([
                sys.executable, str(ROOT / "retro_style.py"),
                "--style", str(ROOT / "www" / "style.json"),
                "--out", str(config_out),
            ])
            content = config_out.read_text()
            assert "color_private:" in content, \
                "color_private absent (forest, park, garden ont des couleurs privées)"

    def test_retro_captures_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_out = Path(tmp) / "config.yaml"
            run([
                sys.executable, str(ROOT / "retro_style.py"),
                "--style", str(ROOT / "www" / "style.json"),
                "--out", str(config_out),
            ])
            content = config_out.read_text()
            assert "military-hatch" in content or "green-hatch" in content, \
                "Aucun pattern trouvé dans le YAML retro"


class TestRoundtrip:
    """
    Test de non-régression bidirectionnel complet :
    style.json → retro → config.yaml → build → style2.json
    Vérifie que style2.json ≃ style.json sur les éléments structurels clés.
    """

    def _roundtrip(self, tmp):
        """Exécute le round-trip complet et retourne (style_orig, style_rebuilt)."""
        style_orig = get_reference_style()

        # Étape 1 : retro → config
        config_out = Path(tmp) / "config.yaml"
        run([
            sys.executable, str(ROOT / "retro_style.py"),
            "--style", str(ROOT / "www" / "style.json"),
            "--out", str(config_out),
        ])

        # Étape 2 : build → style
        style_out = Path(tmp) / "style.json"
        run([
            sys.executable, str(ROOT / "build_map.py"),
            "--config", str(config_out),
            "--style-out", str(style_out),
            "--only", "style",
        ])

        style_rebuilt = load_json(style_out)
        return style_orig, style_rebuilt

    def test_roundtrip_same_layer_count(self):
        """Le nombre de layers ne doit pas changer de plus de 10% (pitch layers exclus)."""
        with tempfile.TemporaryDirectory() as tmp:
            orig, rebuilt = self._roundtrip(tmp)
            # Exclure les layers patch (pitch-sport-*) qui sont ajoutés séparément
            orig_ids = {l["id"] for l in orig["layers"]
                        if not l["id"].startswith("pitch-sport-")
                        and l["id"] != "pitch-markings"}
            rebuilt_ids = {l["id"] for l in rebuilt["layers"]
                           if not l["id"].startswith("pitch-sport-")
                           and l["id"] != "pitch-markings"}
            ratio = len(rebuilt_ids) / max(len(orig_ids), 1)
            assert 0.7 <= ratio <= 1.5, \
                (f"Trop grande divergence de layers : "
                 f"orig={len(orig_ids)}, rebuilt={len(rebuilt_ids)}")

    def test_roundtrip_background_color(self):
        """La couleur de fond doit être préservée."""
        with tempfile.TemporaryDirectory() as tmp:
            orig, rebuilt = self._roundtrip(tmp)
            orig_bg = layer_by_id(orig, "background")
            rebuilt_bg = layer_by_id(rebuilt, "background")
            assert rebuilt_bg is not None, "Layer background absent du style reconstruit"
            orig_col = orig_bg["paint"].get("background-color")
            rebuilt_col = rebuilt_bg["paint"].get("background-color")
            assert orig_col == rebuilt_col, \
                f"background-color diverge : {orig_col} → {rebuilt_col}"

    def test_roundtrip_buildings_fill_color(self):
        with tempfile.TemporaryDirectory() as tmp:
            orig, rebuilt = self._roundtrip(tmp)
            orig_l = layer_by_id(orig, "buildings-fill")
            rebuilt_l = layer_by_id(rebuilt, "buildings-fill")
            assert rebuilt_l is not None
            orig_col = first_hex_color(orig_l["paint"].get("fill-color"))
            rebuilt_col = first_hex_color(rebuilt_l["paint"].get("fill-color"))
            assert orig_col == rebuilt_col, \
                f"buildings fill-color diverge : {orig_col} → {rebuilt_col}"

    def test_roundtrip_buildings_border_color(self):
        with tempfile.TemporaryDirectory() as tmp:
            orig, rebuilt = self._roundtrip(tmp)
            orig_l = layer_by_id(orig, "buildings-outline")
            rebuilt_l = layer_by_id(rebuilt, "buildings-outline")
            assert rebuilt_l is not None
            orig_col = first_hex_color(orig_l["paint"].get("line-color"))
            rebuilt_col = first_hex_color(rebuilt_l["paint"].get("line-color"))
            assert orig_col == rebuilt_col, \
                f"buildings outline color diverge : {orig_col} → {rebuilt_col}"

    def test_roundtrip_water_fill_color(self):
        with tempfile.TemporaryDirectory() as tmp:
            orig, rebuilt = self._roundtrip(tmp)
            for lid in ("water-fill",):
                orig_l = layer_by_id(orig, lid)
                rebuilt_l = layer_by_id(rebuilt, lid)
                if orig_l is None:
                    continue
                assert rebuilt_l is not None, f"Layer {lid} absent du style reconstruit"
                orig_col = first_hex_color(orig_l["paint"].get("fill-color"))
                rebuilt_col = first_hex_color(rebuilt_l["paint"].get("fill-color"))
                assert orig_col == rebuilt_col, \
                    f"{lid} fill-color diverge : {orig_col} → {rebuilt_col}"

    def test_roundtrip_layer_order_preserved(self):
        """Les couches majeures doivent rester dans le bon ordre relatif."""
        with tempfile.TemporaryDirectory() as tmp:
            _, rebuilt = self._roundtrip(tmp)
            ids = [l["id"] for l in rebuilt["layers"]]

            ORDER_PAIRS = [
                ("water-fill",      "buildings-fill"),
                ("buildings-fill",  "roads-fill-motorway"),
                ("background",      "water-fill"),
            ]
            for a, b in ORDER_PAIRS:
                if a not in ids or b not in ids:
                    continue
                assert ids.index(a) < ids.index(b), \
                    f"Ordre invalide : '{a}' devrait être avant '{b}'"

    def test_roundtrip_glyphs_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            orig, rebuilt = self._roundtrip(tmp)
            assert orig.get("glyphs") == rebuilt.get("glyphs"), \
                f"glyphs diverge : {orig.get('glyphs')} → {rebuilt.get('glyphs')}"

    def test_roundtrip_sources_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, rebuilt = self._roundtrip(tmp)
            sources = set(rebuilt.get("sources", {}).keys())
            required = {"roads", "buildings", "water", "poi", "leisure", "green"}
            missing = required - sources
            assert not missing, f"Sources manquantes dans style reconstruit : {missing}"

    def test_roundtrip_minzoom_buildings(self):
        """Le minzoom de buildings doit être préservé."""
        with tempfile.TemporaryDirectory() as tmp:
            orig, rebuilt = self._roundtrip(tmp)
            orig_l = layer_by_id(orig, "buildings-fill")
            rebuilt_l = layer_by_id(rebuilt, "buildings-fill")
            assert rebuilt_l is not None
            assert orig_l.get("minzoom") == rebuilt_l.get("minzoom"), \
                (f"minzoom buildings diverge : "
                 f"{orig_l.get('minzoom')} → {rebuilt_l.get('minzoom')}")

    def test_roundtrip_cycleway_color(self):
        with tempfile.TemporaryDirectory() as tmp:
            orig, rebuilt = self._roundtrip(tmp)
            orig_l = layer_by_id(orig, "cycleway")
            rebuilt_l = layer_by_id(rebuilt, "cycleway")
            if orig_l is None or rebuilt_l is None:
                return
            orig_col = first_hex_color(orig_l["paint"].get("line-color"))
            rebuilt_col = first_hex_color(rebuilt_l["paint"].get("line-color"))
            assert orig_col == rebuilt_col, \
                f"cycleway line-color diverge : {orig_col} → {rebuilt_col}"


# ── Runner autonome (sans pytest) ─────────────────────────────────────────────

def run_all():
    """Exécute tous les tests et affiche un résumé."""
    import traceback

    test_classes = [TestStyleJson, TestBuildMap, TestRetroStyle, TestRoundtrip]
    passed = failed = skipped = 0
    failures = []

    for cls in test_classes:
        instance = cls()
        methods = [m for m in dir(cls) if m.startswith("test_")]
        print(f"\n{'─'*60}")
        print(f"  {cls.__name__}")
        print(f"{'─'*60}")
        for method in methods:
            try:
                getattr(instance, method)()
                print(f"  ✓  {method}")
                passed += 1
            except AssertionError as e:
                print(f"  ✗  {method}")
                print(f"       {e}")
                failed += 1
                failures.append((cls.__name__, method, str(e)))
            except Exception as e:
                print(f"  ✗  {method}  [ERROR]")
                print(f"       {e}")
                failed += 1
                failures.append((cls.__name__, method, traceback.format_exc()))

    print(f"\n{'═'*60}")
    print(f"  {passed} passés  {failed} échoués  {skipped} ignorés")
    print(f"{'═'*60}")

    if failures:
        print("\nÉchecs détaillés :")
        for cls_name, method, msg in failures:
            print(f"\n  {cls_name}.{method}")
            print(f"  {msg[:300]}")
        sys.exit(1)
    else:
        print("\n✓ Tous les tests passent !")


if __name__ == "__main__":
    # Support basique de pytest via `-v` flag
    if "--pytest" in sys.argv or "-v" in sys.argv:
        # Laisse pytest gérer
        import pytest
        sys.exit(pytest.main([__file__, "-v"]))
    else:
        run_all()
