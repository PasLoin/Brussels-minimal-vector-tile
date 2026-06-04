# Brussels minimal vector tile

Is it possible to run Brussels on a minimal vector tile on github page ?

Prototype de carte MapLibre pour la Région de Bruxelles-Capitale, générée à partir d'un extrait OpenStreetMap PBF local et publiée comme fichiers PMTiles statiques dans `www/`.

L'objectif est de garder un jeu de tuiles vectorielles minimal, lisible et versionnable pour GitHub Pages : une couche PMTiles par thème, un style MapLibre unique, et une suite de tests qui vérifie à la fois le style, l'interface et le rendu dans un navigateur.

## Prérequis système

Installez les outils suivants avant de régénérer les données :

| Outil | Usage dans ce dépôt | Vérification rapide |
| :--- | :--- | :--- |
| `osmium` / `osmium-tool` | Filtrer le PBF OSM et exporter les GeoJSON intermédiaires. | `osmium --version` |
| `tippecanoe` | Convertir les GeoJSON en archives PMTiles. | `tippecanoe --version` |
| `python3` | Exécuter les scripts d'enrichissement des couches. | `python3 --version` |
| Node.js + npm | Installer et lancer Vitest, Playwright et les validateurs JS. | `node --version && npm --version` |
| Navigateurs Playwright | Exécuter les tests E2E Chromium desktop/mobile. | `npx playwright install chromium` |

Dépendances Python utilisées par les scripts :

```bash
pip install pyyaml shapely pytest
```

Dépendances Node :

```bash
npm install
npx playwright install chromium
```

## Vue d'ensemble du dépôt

- `brussels_capital_region-latest.osm.pbf` : extrait source OpenStreetMap attendu par le pipeline.
- `map.config.yaml` : **source de vérité du style**. Modifier ce fichier, pas `www/style.json` directement.
- `build_map.py` : compile `map.config.yaml` → `www/style.json` + `granulometry.json` + `pmtiles_params.json`.
- `retro_style.py` : ingénierie inverse d'un `style.json` existant → `map.config.yaml` (bootstrap ou import).
- `generate_json.bash` : extrait les couches thématiques depuis le PBF et produit les GeoJSON intermédiaires (`roads.json`, `poi.json`, etc.).
- `apply_granulometry.py` : filtre les GeoJSON selon les règles LOD générées par `build_map.py`.
- `compute_pitch_bearing.py`, `patch_style_pitches.py`, `extract_stib_routes.py`, `merge_buildings.py` : enrichissements appliqués aux GeoJSON ou au style.
- `generate_poi_icons.py` : génère `www/poi-icons.json` et `missing-icons.txt` à partir des types POI réellement présents.
- `generate_pmtiles.bash` : convertit les GeoJSON en PMTiles et met à jour `sizepmtiles.md`.
- `www/` : application statique, style MapLibre, icônes et PMTiles publiables.
- `tests/` : tests unitaires Vitest, tests E2E Playwright, validation du style et tests Python de non-régression.

---

## Modifier le style de la carte

> **Règle principale : ne jamais éditer `www/style.json` directement.**
> Ce fichier est généré automatiquement par `build_map.py` à partir de `map.config.yaml`.

### Cycle de travail normal

```
map.config.yaml  →  build_map.py  →  www/style.json
```

1. Éditez `map.config.yaml` (couleurs, zooms, opacités, sous-types…).
2. Régénérez le style :

```bash
python3 build_map.py
```

3. Vérifiez visuellement (voir [Serveur local](#serveur-local)).
4. Commitez `map.config.yaml` **et** `www/style.json`.

### Champs disponibles dans `map.config.yaml`

**Niveau couche :**

| Champ | Description |
| :--- | :--- |
| `label` | Nom lisible de la couche |
| `color` | Couleur principale (fill ou line) |
| `border_color` | Couleur du contour (ex : buildings) |
| `appear_at` | Zoom minimum d'apparition |
| `labels_at` | Zoom minimum des étiquettes (défaut : `appear_at + 3`) |
| `opacity` | Opacité globale (0.0–1.0) |
| `visible` | `false` pour masquer la couche |
| `extrusion_3d` | `true` pour activer le rendu 3D des bâtiments |

**Niveau sous-type (`subtypes`) :**

| Champ | Description |
| :--- | :--- |
| `tag` | Tag OSM du filtre (`landuse`, `leisure`, `highway`…) |
| `color` | Couleur principale du sous-type |
| `color_private` | Couleur si `access=private` |
| `pattern` | `fill-pattern` (ex : `military-hatch`) |
| `pattern_private` | `fill-pattern` uniquement si `access=private` (ex : `green-hatch`) |
| `outline_color` | Couleur du contour |
| `appear_at` | Zoom minimum pour ce sous-type |
| `opacity` | Opacité fill (0.0–1.0) |

### Importer un style externe (bootstrap `retro_style.py`)

Si vous disposez d'un `style.json` MapLibre existant (Maputnik, import externe…) et souhaitez en faire la source de vérité, utilisez `retro_style.py` pour en extraire automatiquement un `map.config.yaml` :

```bash
python3 retro_style.py --style www/style.json --out map.config.yaml
```

Ce script extrait couleurs, `border_color`, `appear_at`, `labels_at`, `extrusion_3d`, opacités, `color_private`, patterns et sous-types pour toutes les couches reconnues.

> **Attention :** si `map.config.yaml` existe déjà, ajoutez `--out map.config.new.yaml` pour ne pas l'écraser, puis comparez.

Le workflow GitHub `retro.yml` fait la même chose en un clic depuis l'onglet **Actions** :

1. Actions → *Retro-engineer config from style* → **Run workflow**
2. Choisissez `overwrite: true` pour écraser l'existant, ou laissez `false` pour créer un fichier parallèle.
3. Le fichier YAML généré est commité automatiquement.

### Garantie bidirectionnelle

La chaîne est conçue pour être réversible sans perte :

```
map.config.yaml  →  build_map.py   →  www/style.json
www/style.json   →  retro_style.py →  map.config.yaml  →  build_map.py  →  www/style.json (≃ identique)
```

Les tests de non-régression Python (`tests/test_roundtrip.py`) vérifient automatiquement cette propriété à chaque PR.

---

## Workflow de développement complet

L'ordre recommandé est : **config → extraction → LOD → PMTiles → validation → tests**.

### 1. Modifier le style (si besoin)

```bash
# Éditer map.config.yaml, puis :
python3 build_map.py
```

### 2. Extraction des couches GeoJSON

```bash
./generate_json.bash
```

Cette commande lit `brussels_capital_region-latest.osm.pbf`, vérifie que le fichier est bien un PBF OSM, puis produit les couches GeoJSON suivantes : `roads`, `buildings`, `water`, `green`, `trees`, `landuse`, `boundaries`, `poi`, `leisure`, `pedestrian`, `cycleway`, `railway` et `public_transport`.

À cette étape, les POI surfaciques sont convertis en points représentatifs et dédoublonnés. La couche `public_transport` est reconstruite depuis les relations STIB/MIVB.

### 3. Enrichissement des données et du style

```bash
python3 merge_buildings.py
python3 patch_style_pitches.py
python3 generate_poi_icons.py
```

- `merge_buildings.py` produit `buildings_merged.json` pour les zooms bas, tout en conservant `buildings_detail.json` pour les zooms hauts.
- `patch_style_pitches.py` synchronise le style avec les orientations calculées pour les terrains de sport.
- `generate_poi_icons.py` inspecte `poi.json`, résout les icônes locales/CDN disponibles, écrit `www/poi-icons.json`, puis liste les manques dans `missing-icons.txt`.

> `generate_json.bash` lance déjà `compute_pitch_bearing.py` après l'extraction de `leisure.json`. Relancez `compute_pitch_bearing.py` manuellement uniquement si vous modifiez `leisure.json` sans refaire toute l'extraction.

### 4. Application de la granulométrie (LOD)

```bash
python3 apply_granulometry.py
```

Filtre les GeoJSON selon les règles LOD définies dans `granulometry.json` (généré par `build_map.py`). Les features hors zoom d'apparition sont supprimées ; les propriétés sont allégées aux zooms bas pour réduire la taille des tuiles.

```bash
# Simuler sans écrire (dry-run) :
python3 apply_granulometry.py --dry-run

# Appliquer uniquement certaines couches :
python3 apply_granulometry.py --layers roads,poi
```

### 5. Génération des PMTiles

```bash
./generate_pmtiles.bash
```

Le script produit un fichier `.pmtiles.gz` par source vectorielle et met à jour le rapport `sizepmtiles.md`. Les fichiers générés à la racine doivent ensuite remplacer ceux de `www/` :

```bash
mv *.pmtiles.gz www/
```

> **Note sur l'extension `.pmtiles.gz`** : les fichiers sont des archives PMTiles v3 valides renommés en `.pmtiles.gz`. Ce renommage est un contournement d'une limitation de GitHub Pages qui ne sert pas correctement les fichiers `.pmtiles` (Content-Type incorrect). Le fichier n'est pas compressé une seconde fois : la compression interne du format PMTiles est conservée. Aucun outil ne doit tenter de décompresser ces fichiers comme un `.gz` standard.

Les sources déclarées dans `www/style.json` doivent correspondre aux noms des PMTiles publiés dans `www/`.

### 6. Validation du style et des PMTiles

Validation rapide utilisée par npm :

```bash
npm run test:validate
```

Validation stricte avec lecture des métadonnées PMTiles :

```bash
mkdir -p tmp/pmtiles-metadata
python3 scripts/extract_pmtiles_metadata.py www/*.pmtiles.gz --out-dir tmp/pmtiles-metadata
python3 scripts/validate_style_pmtiles.py --style www/style.json --metadata-dir tmp/pmtiles-metadata
```

La première commande extrait les métadonnées PMTiles. La seconde vérifie que chaque layer vectoriel de `www/style.json` référence une source existante et un `source-layer` réellement présent dans le PMTiles.

### 7. Tests unitaires et E2E

Tests unitaires :

```bash
npm test
```

Tests unitaires en mode watch :

```bash
npm run test:watch
```

Couverture Vitest :

```bash
npm run test:coverage
```

Tests Python de non-régression (round-trip `retro_style` ↔ `build_map`) :

```bash
python3 -m pytest tests/test_roundtrip.py -v
```

Tests E2E Playwright :

```bash
npm run test:e2e
```

Playwright démarre automatiquement un serveur statique sur `http://localhost:8080` via `playwright.config.js`. Pour tester manuellement l'application :

```bash
npm run serve
```

Suite complète :

```bash
npm run test:all
```

---

## Mettre à jour le PBF

Le pipeline attend un fichier nommé exactement `brussels_capital_region-latest.osm.pbf` à la racine du dépôt.

```bash
curl -L \
  -o brussels_capital_region-latest.osm.pbf \
  https://download.openstreetmap.fr/extracts/europe/belgium/brussels_capital_region.osm.pbf
file brussels_capital_region-latest.osm.pbf
osmium fileinfo brussels_capital_region-latest.osm.pbf
```

Après remplacement du PBF, relancez le workflow complet :

```bash
python3 build_map.py
./generate_json.bash
python3 merge_buildings.py
python3 apply_granulometry.py
python3 patch_style_pitches.py
python3 generate_poi_icons.py
./generate_pmtiles.bash
mv *.pmtiles.gz www/
npm run test:validate
python3 -m pytest tests/test_roundtrip.py -v
npm test
npm run test:e2e
```

Si vous préférez une source OSM différente, conservez le même nom de fichier ou modifiez la variable `SRC` dans `generate_json.bash`.

---

## Ajouter une couche

Ajouter une couche implique de modifier les trois parties du pipeline : extraction, tuilage, style.

1. **Extraire les objets OSM** dans `generate_json.bash`.
   - Ajoutez un appel `extract nouvelle_couche ...` pour un filtrage simple.
   - Pour une extraction relationnelle ou une transformation avancée, suivez le modèle de `public_transport` ou ajoutez un script Python dédié.
2. **Déclarer la couche dans `map.config.yaml`** avec ses couleurs et zooms, puis régénérez :
   ```bash
   python3 build_map.py
   ```
3. **Appliquer la granulométrie** (optionnel) : les règles LOD sont auto-générées par `build_map.py`. Vérifiez `granulometry.json` puis relancez `apply_granulometry.py`.
4. **Générer le PMTiles** dans `generate_pmtiles.bash`.
   - Ajoutez la couche aux tableaux `MAX_ZOOM` et `SIMPLIFICATION`.
   - Ajoutez son nom dans la boucle des couches standard, sauf si elle nécessite une commande Tippecanoe spéciale comme `buildings`.
5. **Publier le fichier** dans `www/`.
   - Après génération, déplacez `nouvelle_couche.pmtiles.gz` vers `www/`.
6. **Déclarer la source MapLibre** dans `www/style.json`.
   - La source est ajoutée automatiquement par `build_map.py` si la couche est déclarée dans `map.config.yaml`.
7. **Valider**.
   - Lancez `npm run test:validate`, puis `python3 -m pytest tests/test_roundtrip.py -v`.
   - Ajoutez ou adaptez des tests dans `tests/unit/` ou `tests/e2e/` si l'interface, la légende ou les layers visibles changent.

---

## Ajouter une icône POI

Les icônes POI sont résolues par `www/poi_icons.js` à partir du manifeste `www/poi-icons.json`. Ce manifeste est généré par `generate_poi_icons.py`.

1. Identifiez la clé OSM qui doit produire l'icône.
   - Exemple simple : `shop=butcher` produit le type `butcher`.
   - Exemple sous-type : `cuisine=friture` produit la clé `cuisine-friture`.
2. Ajoutez un SVG local dans `www/assets/icons/` si aucune icône CDN ne convient.
   - Utilisez un nom explicite et stable, par exemple `www/assets/icons/butcher.svg`.
3. Si le nom local/CDN ne correspond pas à la clé POI, ajoutez ou ajustez l'entrée dans `CDN_NAME_OVERRIDES` dans `generate_poi_icons.py`.
   - Les overrides peuvent pointer vers un fichier local (`local`) ou vers un nom d'icône Temaki, Maki ou Liberty.
4. Regénérez le manifeste :

```bash
python3 generate_poi_icons.py
```

5. Vérifiez les manques restants :

```bash
cat missing-icons.txt
npm test -- tests/unit/poi_icons.test.js
```

6. Lancez les tests E2E si l'icône modifie le rendu visible de la carte ou de la légende.

---

## Commandes utiles

| Commande | Description |
| :--- | :--- |
| `python3 build_map.py` | Compile `map.config.yaml` → `www/style.json` + granulométrie + params PMTiles. |
| `python3 retro_style.py` | Ingénierie inverse `www/style.json` → `map.config.yaml`. |
| `python3 apply_granulometry.py` | Applique les règles LOD aux GeoJSON. |
| `npm run serve` | Sert `www/` sur le port 8080 pour inspection locale. |
| `npm test` | Lance les tests unitaires Vitest. |
| `npm run test:watch` | Lance Vitest en mode interactif. |
| `npm run test:coverage` | Produit la couverture des tests unitaires. |
| `npm run test:validate` | Valide la cohérence de `www/style.json` et des assets attendus. |
| `npm run test:e2e` | Lance les tests Playwright desktop et mobile. |
| `npm run test:e2e:ui` | Ouvre l'interface Playwright. |
| `npm run test:e2e:report` | Affiche le dernier rapport Playwright. |
| `npm run test:all` | Lance unitaires, validation de style et E2E. |
| `python3 -m pytest tests/test_roundtrip.py -v` | Tests de non-régression Python (round-trip style ↔ config). |

---

## Connus et limitations

### Extension `.pmtiles.gz`

Les fichiers produits sont des PMTiles v3 valides renommés en `.pmtiles.gz`. Ce renommage contourne une limitation de GitHub Pages qui ne sert pas correctement les fichiers `.pmtiles` (Content-Type non reconnu). Le fichier n'est **pas** une archive gzip : la compression interne PMTiles est intacte, et aucun outil externe ne doit le décompresser comme un `.gz` standard.

### CSS inline et handlers inline

La page `www/index.html` contient actuellement du CSS inline et des handlers `onclick` inline. Cela fonctionne mais complexifie une future politique CSP stricte. Une refactorisation vers `www/style.css` + `addEventListener` est planifiée.

---

## Dépannage

- **`brussels_capital_region-latest.osm.pbf n'est pas un fichier PBF valide`** : le téléchargement a probablement renvoyé une page HTML ou un fichier incomplet. Relancez le téléchargement et vérifiez `file ...`.
- **`tippecanoe: command not found`** : installez Tippecanoe et vérifiez qu'il est dans le `PATH`.
- **Icônes POI manquantes** : consultez `missing-icons.txt`, ajoutez un SVG local ou un override, puis relancez `python3 generate_poi_icons.py`.
- **Playwright ne trouve pas Chromium** : lancez `npx playwright install chromium`.
- **Le style référence une couche absente** : comparez `www/style.json`, les noms de fichiers `www/*.pmtiles.gz` et les `vector_layers` extraits par `scripts/extract_pmtiles_metadata.py`.
- **`map.config.yaml` et `www/style.json` divergent** : lancez `python3 build_map.py` pour régénérer le style depuis la config, ou `python3 retro_style.py` pour reconstruire la config depuis le style.
- **Les tests round-trip échouent** : comparez le YAML généré par `retro_style.py` avec `map.config.yaml` de référence. Les divergences indiquent un champ non capturé par `retro_style.py` ou un comportement de `build_map.py` qui n'a pas d'équivalent dans la config.
