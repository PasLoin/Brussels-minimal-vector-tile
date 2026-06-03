
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
python3 -m pip install shapely
```

Dépendances Node :

```bash
npm install
npx playwright install chromium
```

## Vue d'ensemble du dépôt

- `brussels_capital_region-latest.osm.pbf` : extrait source OpenStreetMap attendu par le pipeline.
- `generate_json.bash` : extrait les couches thématiques depuis le PBF et produit les GeoJSON intermédiaires (`roads.json`, `poi.json`, etc.).
- `compute_pitch_bearing.py`, `patch_style_pitches.py`, `extract_stib_routes.py`, `merge_buildings.py` : enrichissements appliqués aux GeoJSON ou au style.
- `generate_poi_icons.py` : génère `www/poi-icons.json` et `missing-icons.txt` à partir des types POI réellement présents.
- `generate_pmtiles.bash` : convertit les GeoJSON en PMTiles et met à jour `sizepmtiles.md`.
- `www/` : application statique, style MapLibre, icônes et PMTiles publiables.
- `tests/` : tests unitaires Vitest, tests E2E Playwright et validation du style.

## Workflow de développement complet

L'ordre recommandé est : **extraction → enrichissement → PMTiles → validation → tests**.

### 1. Extraction des couches GeoJSON

```bash
./generate_json.bash
```

Cette commande lit `brussels_capital_region-latest.osm.pbf`, vérifie que le fichier est bien un PBF OSM, puis produit les couches GeoJSON suivantes : `roads`, `buildings`, `water`, `green`, `trees`, `landuse`, `boundaries`, `poi`, `leisure`, `pedestrian`, `cycleway`, `railway` et `public_transport`.

À cette étape, les POI surfaciques sont convertis en points représentatifs et dédoublonnés. La couche `public_transport` est reconstruite depuis les relations STIB/MIVB.

### 2. Enrichissement des données et du style

```bash
python3 merge_buildings.py
python3 patch_style_pitches.py
python3 generate_poi_icons.py
```

- `merge_buildings.py` produit `buildings_merged.json` pour les zooms bas, tout en conservant `buildings_detail.json` pour les zooms hauts.
- `patch_style_pitches.py` synchronise le style avec les orientations calculées pour les terrains de sport.
- `generate_poi_icons.py` inspecte `poi.json`, résout les icônes locales/CDN disponibles, écrit `www/poi-icons.json`, puis liste les manques dans `missing-icons.txt`.

> `generate_json.bash` lance déjà `compute_pitch_bearing.py` après l'extraction de `leisure.json`. Relancez `compute_pitch_bearing.py` manuellement uniquement si vous modifiez `leisure.json` sans refaire toute l'extraction.

### 3. Génération des PMTiles

```bash
./generate_pmtiles.bash
```

Le script produit un fichier `.pmtiles.gz` par source vectorielle et met à jour le rapport `sizepmtiles.md`. Les fichiers générés à la racine doivent ensuite remplacer ceux de `www/` :

```bash
mv *.pmtiles.gz www/
```

Les sources déclarées dans `www/style.json` doivent correspondre aux noms des PMTiles publiés dans `www/`.

### 4. Validation du style et des PMTiles

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

### 5. Tests unitaires et E2E

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
./generate_json.bash
python3 merge_buildings.py
python3 patch_style_pitches.py
python3 generate_poi_icons.py
./generate_pmtiles.bash
mv *.pmtiles.gz www/
npm run test:validate
npm test
npm run test:e2e
```

Si vous préférez une source OSM différente, conservez le même nom de fichier ou modifiez la variable `SRC` dans `generate_json.bash`.

## Ajouter une couche

Ajouter une couche implique de modifier les trois parties du pipeline : extraction, tuilage, style.

1. **Extraire les objets OSM** dans `generate_json.bash`.
   - Ajoutez un appel `extract nouvelle_couche ...` pour un filtrage simple.
   - Pour une extraction relationnelle ou une transformation avancée, suivez le modèle de `public_transport` ou ajoutez un script Python dédié.
2. **Générer le PMTiles** dans `generate_pmtiles.bash`.
   - Ajoutez la couche aux tableaux `MAX_ZOOM` et `SIMPLIFICATION`.
   - Ajoutez son nom dans la boucle des couches standard, sauf si elle nécessite une commande Tippecanoe spéciale comme `buildings`.
3. **Publier le fichier** dans `www/`.
   - Après génération, déplacez `nouvelle_couche.pmtiles.gz` vers `www/`.
4. **Déclarer la source MapLibre** dans `www/style.json`.
   - Ajoutez une entrée dans `sources` avec `"type": "vector"` et `"url": "pmtiles://./nouvelle_couche.pmtiles.gz"`.
5. **Ajouter les layers de rendu** dans `www/style.json`.
   - Chaque layer vectoriel doit définir `source: "nouvelle_couche"` et `source-layer: "nouvelle_couche"`.
6. **Valider**.
   - Lancez `npm run test:validate`, puis les validations PMTiles strictes si vous avez régénéré les archives.
   - Ajoutez ou adaptez des tests dans `tests/unit/` ou `tests/e2e/` si l'interface, la légende ou les layers visibles changent.

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

## Commandes utiles

| Commande | Description |
| :--- | :--- |
| `npm run serve` | Sert `www/` sur le port 8080 pour inspection locale. |
| `npm test` | Lance les tests unitaires Vitest. |
| `npm run test:watch` | Lance Vitest en mode interactif. |
| `npm run test:coverage` | Produit la couverture des tests unitaires. |
| `npm run test:validate` | Valide la cohérence de `www/style.json` et des assets attendus. |
| `npm run test:e2e` | Lance les tests Playwright desktop et mobile. |
| `npm run test:e2e:ui` | Ouvre l'interface Playwright. |
| `npm run test:e2e:report` | Affiche le dernier rapport Playwright. |
| `npm run test:all` | Lance unitaires, validation de style et E2E. |

## Dépannage

- **`brussels_capital_region-latest.osm.pbf n'est pas un fichier PBF valide`** : le téléchargement a probablement renvoyé une page HTML ou un fichier incomplet. Relancez le téléchargement et vérifiez `file ...`.
- **`tippecanoe: command not found`** : installez Tippecanoe et vérifiez qu'il est dans le `PATH`.
- **Icônes POI manquantes** : consultez `missing-icons.txt`, ajoutez un SVG local ou un override, puis relancez `python3 generate_poi_icons.py`.
- **Playwright ne trouve pas Chromium** : lancez `npx playwright install chromium`.
- **Le style référence une couche absente** : comparez `www/style.json`, les noms de fichiers `www/*.pmtiles.gz` et les `vector_layers` extraits par `scripts/extract_pmtiles_metadata.py`.
