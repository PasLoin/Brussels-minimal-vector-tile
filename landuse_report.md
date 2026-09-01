# Landuse coverage report

Comparaison entre les `landuse=*` présents dans l'extrait Bruxelles et ceux rendus par `map.config.yaml` (cf. issue #37).

- ✓ rendus : 20
- ⚠ manquants (présents mais sans style) : 10
- ↪ gérés par une autre couche : 5
- · sans donnée dans le pbf Bxl : 7

## ⚠ Présents dans Bxl mais non rendus

Ces valeurs existent dans le pbf mais n'ont pas de sous-type dans `layers.landuse.subtypes` → ajouter un rendu.

| landuse | features |
| :--- | ---: |
| `plant_nursery` | 32 |
| `orchard` | 26 |
| `traffic_island` | 10 |
| `animal_keeping` | 6 |
| `greenery` | 6 |
| `institutional` | 6 |
| `vineyard` | 6 |
| `greenhouse_horticulture` | 4 |
| `shrubs` | 4 |
| `parking` | 2 |

## ✓ Rendus

| landuse | features |
| :--- | ---: |
| `residential` | 2299 |
| `commercial` | 452 |
| `construction` | 337 |
| `industrial` | 315 |
| `allotments` | 288 |
| `farmland` | 242 |
| `railway` | 189 |
| `village_green` | 158 |
| `garages` | 126 |
| `brownfield` | 117 |
| `retail` | 100 |
| `recreation_ground` | 66 |
| `cemetery` | 64 |
| `education` | 54 |
| `farmyard` | 46 |
| `greenfield` | 46 |
| `military` | 8 |
| `landfill` | 4 |
| `quarry` | 4 |
| `religious` | 2 |

## ↪ Gérés par une autre couche

| landuse | features | couche |
| :--- | ---: | :--- |
| `grass` | 9505 | green (green.json) |
| `forest` | 884 | green (green.json, via natural=wood + landuse=forest) |
| `flowerbed` | 555 | green (green.json) |
| `meadow` | 501 | green (green.json) |
| `basin` | 2 | water (water.json) |

## · Sans donnée dans le pbf Bxl

Configurés et/ou listés par le wiki OSM, mais absents de l'extrait actuel — aucun rendu généré (conforme : on ne rend pas ce qui n'existe pas dans les données).

| landuse | configuré dans map.config.yaml ? |
| :--- | :---: |
| `aquaculture` | non |
| `conservation` | non |
| `depot` | oui |
| `harbour` | non |
| `port` | non |
| `salt_pond` | non |
| `winter_sports` | non |

