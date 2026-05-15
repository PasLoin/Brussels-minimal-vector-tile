#!/usr/bin/env python3
"""
patch_style_pitches.py
──────────────────────
Insère les couches de rendu des terrains de sport dans style.json :
  1. Fill spécifique par sport (couleur de surface distincte)
  2. Marquage des lignes via symbol+icon-image rotatif

Idempotent : détecte les couches déjà présentes et ne les ajoute pas.
Peut tourner à chaque build sur le style.json propre du repo.
Usage : python3 patch_style_pitches.py [www/style.json]
"""
import json
import sys

STYLE_PATH = sys.argv[1] if len(sys.argv) > 1 else "www/style.json"

# ─── Couleurs de surface par sport ────────────────────────
PITCH_FILLS = {
    "soccer":     "#5a9e4b",
    "tennis":     "#4a7c3f",
    "basketball": "#c47a4a",
}
PITCH_FILL_DEFAULT = "#8ad3af"   # fallback (leisure-fill d'origine)

# ─── Nouvelles couches ────────────────────────────────────

# 1. Fill coloré par sport (remplace le vert générique pour les pitchs avec sport_render)
PITCH_SPORT_FILL = {
    "id": "pitch-sport-fill",
    "type": "fill",
    "source": "leisure",
    "source-layer": "leisure",
    "filter": [
        "all",
        ["==", ["get", "leisure"], "pitch"],
        ["has", "sport_render"],
        ["==", ["geometry-type"], "Polygon"],
    ],
    "paint": {
        "fill-color": [
            "match", ["get", "sport_render"],
            "soccer",     PITCH_FILLS["soccer"],
            "tennis",     PITCH_FILLS["tennis"],
            "basketball", PITCH_FILLS["basketball"],
            PITCH_FILL_DEFAULT,
        ],
        "fill-opacity": 1.0,
    },
}

# 2. Contour du terrain de sport
PITCH_SPORT_OUTLINE = {
    "id": "pitch-sport-outline",
    "type": "line",
    "source": "leisure",
    "source-layer": "leisure",
    "filter": [
        "all",
        ["==", ["get", "leisure"], "pitch"],
        ["has", "sport_render"],
        ["==", ["geometry-type"], "Polygon"],
    ],
    "paint": {
        "line-color": [
            "match", ["get", "sport_render"],
            "soccer",     "#3d7a32",
            "tennis",     "#3a6530",
            "basketball", "#9e5e33",
            "#6fb792",
        ],
        "line-width": 0.8,
    },
}

# 3. Marquages sportifs (symbole rotatif)
#
#    À z18 (seul zoom), m/px ≈ 0.377 à Bruxelles.
#    icon_size = longueur_m / (200 px × 0.377 m/px) = longueur_m × 0.01327
#    Utilise pitch_length si disponible, sinon dimensions standard du sport.
#
PITCH_MARKINGS = {
    "id": "pitch-markings",
    "type": "symbol",
    "source": "leisure",
    "source-layer": "leisure",
    "minzoom": 18,
    "filter": [
        "all",
        ["==", ["get", "leisure"], "pitch"],
        ["has", "sport_render"],
        ["==", ["geometry-type"], "Polygon"],
    ],
    "layout": {
        "icon-image": [
            "concat", "sport-markings-", ["get", "sport_render"]
        ],
        "icon-rotation-alignment": "map",
        "icon-pitch-alignment": "map",
        "icon-rotate": ["coalesce", ["get", "bearing"], 0],
        "icon-size": [
            "*",
            [
                "case",
                ["has", "pitch_length"], ["get", "pitch_length"],
                ["match", ["get", "sport_render"],
                    "tennis", 24,
                    "soccer", 105,
                    "basketball", 28,
                    50,
                ],
            ],
            0.01327,
        ],
        "icon-allow-overlap": False,
        "icon-ignore-placement": False,
        "symbol-placement": "point",
    },
    "paint": {
        "icon-opacity": 0.9,
    },
}

# ─── Insertion dans le style ──────────────────────────────

def patch_style(style):
    layers = style["layers"]
    existing_ids = {layer["id"] for layer in layers}

    # Idempotent : si déjà patché, on ne fait rien
    PITCH_IDS = {"pitch-sport-fill", "pitch-sport-outline", "pitch-markings"}
    if PITCH_IDS <= existing_ids:
        print("  (couches pitch déjà présentes — skip)")
        return style

    # Supprimer les couches partielles d'un patch précédent éventuel
    layers[:] = [l for l in layers if l["id"] not in PITCH_IDS]

    # Trouver la position de "leisure-fill" pour insérer juste AVANT
    target_idx = None
    for i, layer in enumerate(layers):
        if layer["id"] == "leisure-fill":
            target_idx = i
            break

    if target_idx is None:
        print("⚠  Couche 'leisure-fill' non trouvée — insertion en fin de liste")
        target_idx = len(layers)

    # Insérer les couches sport AVANT leisure-fill
    # (le fill sport écrasera visuellement leisure-fill pour les pitchs concernés)
    new_layers = [PITCH_SPORT_FILL, PITCH_SPORT_OUTLINE]
    for j, nl in enumerate(new_layers):
        layers.insert(target_idx + j, nl)

    # Insérer les marquages APRÈS les bâtiments (pour qu'ils soient
    # au-dessus), juste avant "poi-circle" ou à la fin
    markings_idx = None
    for i, layer in enumerate(layers):
        if layer["id"] == "poi-circle":
            markings_idx = i
            break
    if markings_idx is None:
        markings_idx = len(layers)

    layers.insert(markings_idx, PITCH_MARKINGS)

    return style


def main():
    with open(STYLE_PATH) as f:
        style = json.load(f)

    style = patch_style(style)

    with open(STYLE_PATH, "w") as f:
        json.dump(style, f, indent=2, ensure_ascii=False)

    print(f"✓ style.json patché : 3 couches ajoutées (pitch-sport-fill, pitch-sport-outline, pitch-markings)")


if __name__ == "__main__":
    main()
