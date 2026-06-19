# Street furniture coverage report

Comparaison entre les tags `amenity=*` / `barrier=*` / `highway=street_lamp` présents dans l'extrait Bruxelles et ceux rendus par `map.config.yaml` (cf. issue #51 — "Streets furnitures, small object (micromapping)").

- ✓ rendus : 12
- ⚠ manquants (présents mais sans style) : 10
- · sans donnée dans le pbf Bxl : 0
- `entrance=*` (toutes valeurs confondues) : 12193 features — rendu (rendu uniforme par clé, pas par valeur)

## ⚠ Présents dans Bxl mais non rendus

Ces valeurs existent dans le pbf mais n'ont pas de sous-type dans `layers.street_furniture.subtypes` → ajouter un rendu dans `map.config.yaml` (et au besoin une icône, voir `missing-icons.txt` après `generate_poi_icons.py`).

| tag | valeur | features |
| :--- | :--- | ---: |
| `amenity` | `bicycle_parking` | 7615 |
| `amenity` | `shelter` | 3666 |
| `barrier` | `block` | 295 |
| `amenity` | `drinking_water` | 155 |
| `barrier` | `swing_gate` | 65 |
| `amenity` | `clock` | 43 |
| `barrier` | `full-height_turnstile` | 27 |
| `barrier` | `stile` | 20 |
| `barrier` | `kissing_gate` | 5 |
| `amenity` | `give_box` | 4 |

## ✓ Rendus

| tag | valeur | features |
| :--- | :--- | ---: |
| `highway` | `street_lamp` | 10193 |
| `amenity` | `bench` | 7530 |
| `barrier` | `bollard` | 7327 |
| `amenity` | `waste_basket` | 6820 |
| `barrier` | `fence` | 4525 |
| `barrier` | `gate` | 3367 |
| `amenity` | `vending_machine` | 1801 |
| `barrier` | `lift_gate` | 840 |
| `barrier` | `cycle_barrier` | 131 |
| `barrier` | `planter` | 72 |
| `amenity` | `lounger` | 42 |
| `barrier` | `bus_trap` | 15 |

## Sous-types `vending=*` (raffinement d'icône)

`amenity=vending_machine` est déjà rendu ci-dessus ; ces valeurs ne créent pas de couche supplémentaire, seulement une icône plus précise si elle existe (même principe que `cuisine=*` / `religion=*` pour les POI — cf. `generate_poi_icons.py` et `missing-icons.txt`).

| vending | features |
| :--- | ---: |
| `parking_tickets` | 1441 |
| `public_transport_tickets` | 229 |
| `excrement_bags` | 63 |
| `newspapers` | 17 |
| `coffee` | 15 |
| `condoms` | 6 |
| `admission_tickets` | 3 |
| `drinks` | 2 |
| `sun_cream` | 2 |
| `sweets` | 1 |
| `candles` | 1 |
| `snacks` | 1 |
| `umbrella` | 1 |
| `sweets;drinks;condoms` | 1 |
| `potatoes;eggs` | 1 |
| `milk` | 1 |
| `chemist` | 1 |
| `souvenirs` | 1 |
| `food` | 1 |
| `drinks;food` | 1 |
| `meat` | 1 |
| `chemist;condoms` | 1 |
| `elongated_coin` | 1 |
| `condoms;menstrual_products` | 1 |

