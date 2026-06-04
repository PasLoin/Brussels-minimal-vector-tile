# How-to : éditer le style de la carte

## Principe général

Le style MapLibre (`www/style.json`) est **généré automatiquement** — ne l'éditez pas à la main.

La source de vérité est `map.config.yaml`. Toute modification de couleur, de zoom ou de sous-type passe par ce fichier, puis par `build_map.py`.

```
map.config.yaml  ──►  build_map.py  ──►  www/style.json
```

---

## Cas 1 — Modifier une couleur ou un zoom

1. Ouvrez `map.config.yaml`.
2. Trouvez la couche concernée et ajustez le champ voulu (`color`, `appear_at`, `opacity`…).
3. Régénérez :

```bash
python3 build_map.py
```

4. Vérifiez dans le navigateur :

```bash
npm run serve
# ouvrir http://localhost:8080
```

5. Commitez les deux fichiers modifiés :

```bash
git add map.config.yaml www/style.json
git commit -m "style: ..."
```

---

## Cas 2 — Travailler depuis Maputnik

Maputnik permet d'éditer le style visuellement, mais produit un `style.json` modifié — pas un `map.config.yaml`.

Pour réintégrer un style édité dans Maputnik :

```bash
# 1. Téléchargez le style depuis Maputnik (bouton Export)
#    et écrasez www/style.json

# 2. Reconstruisez map.config.yaml depuis ce style :
python3 retro_style.py --style www/style.json --out map.config.yaml

# 3. Vérifiez le YAML généré, puis régénérez le style propre :
python3 build_map.py

# 4. Vérifiez que le round-trip n'a pas perdu d'information :
python3 -m pytest tests/test_roundtrip.py -v
```

> Maputnik en ligne avec le style de ce dépôt :
> [maputnik.github.io/editor](https://maputnik.github.io/editor/#15.4/50.832973/4.318494/-1.9/39)
> — charger depuis URL : `https://pmtiles.duckdns.org/brussels_ultimate_style.json`

---

## Cas 3 — Importer un style externe

Même procédure que Maputnik : placez le `style.json` externe dans `www/`, puis lancez `retro_style.py`.

```bash
python3 retro_style.py --style www/style.json --out map.config.yaml
python3 build_map.py
```

Le workflow GitHub `retro.yml` fait la même chose sans ligne de commande :

1. Onglet **Actions** → *Retro-engineer config from style* → **Run workflow**
2. Paramètres :
   - `style_path` : chemin du style source (défaut : `www/style.json`)
   - `config_out` : chemin de sortie (défaut : `map.config.yaml`)
   - `overwrite` : `true` pour écraser l'existant

Le YAML généré est commité automatiquement dans le dépôt.

---

## Référence rapide — champs de `map.config.yaml`

### Niveau couche

```yaml
layers:
  buildings:
    label: Bâtiments          # nom lisible
    color: "#fce1c5"          # couleur principale (fill ou line)
    border_color: "#d4a574"   # couleur du contour
    appear_at: 13             # zoom minimum d'apparition
    labels_at: 16             # zoom minimum des étiquettes (défaut : appear_at + 3)
    opacity: 0.9              # opacité globale (0.0–1.0)
    visible: true             # false pour masquer
    extrusion_3d: true        # rendu 3D (buildings uniquement)
```

### Niveau sous-type

```yaml
    subtypes:
      forest:
        tag: natural               # tag OSM du filtre
        color: "#add19e"           # couleur du sous-type
        color_private: "#d9ecd2"   # couleur si access=private
        pattern: "military-hatch"  # fill-pattern
        pattern_private: "green-hatch"  # fill-pattern si access=private
        outline_color: "#6fb792"   # couleur du contour
        appear_at: 12              # zoom minimum pour ce sous-type
        opacity: 0.8               # opacité
```

---

## Tests de non-régression

Après toute modification du style ou de la config, lancez :

```bash
# Round-trip complet retro_style ↔ build_map
python3 -m pytest tests/test_roundtrip.py -v

# Cohérence style.json ↔ PMTiles ↔ assets
npm run test:validate
```

Ces tests sont aussi lancés automatiquement sur chaque PR par le workflow `.github/workflows/tests.yml`.
