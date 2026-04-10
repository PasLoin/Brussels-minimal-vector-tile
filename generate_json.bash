# 1. MOBILITÉ PIÉTONNE
osmium tags-filter brussels_capital_region-latest.osm.pbf nwr/highway=footway,pedestrian,sidewalk,steps,corridor,crossing -o pedestrian.opl --overwrite && osmium export pedestrian.opl -o pedestrian.json --overwrite

# 2. MOBILITÉ DOUCE
osmium tags-filter brussels_capital_region-latest.osm.pbf nwr/highway=cycleway nwr/bicycle_parking=* -o cycling.opl --overwrite && osmium export cycling.opl -o cycling.json --overwrite

# 3. MOBILIER URBAIN
osmium tags-filter brussels_capital_region-latest.osm.pbf n/amenity=bench,waste_basket,drinking_water,toilets n/barrier=bollard,bicycle_repair_station -o furniture.opl --overwrite && osmium export furniture.opl -o furniture.json --overwrite

# 4. ÉCLAIRAGE ET INFRA
osmium tags-filter brussels_capital_region-latest.osm.pbf n/highway=street_lamp n/man_made=street_cabinet -o infra.opl --overwrite && osmium export infra.opl -o infra.json --overwrite

# 5. NATURE URBAINE
osmium tags-filter brussels_capital_region-latest.osm.pbf n/natural=tree nwr/leisure=park,garden nwr/barrier=hedge -o green.opl --overwrite && osmium export green.opl -o green.json --overwrite

# 6. BÂTIMENTS (Emprises au sol)
osmium tags-filter brussels_capital_region-latest.osm.pbf nwr/building=* -o buildings.opl --overwrite && osmium export buildings.opl -o buildings.json --overwrite

# 7. BÂTIMENTS PARTS (Détails 3D)
osmium tags-filter brussels_capital_region-latest.osm.pbf nwr/building:part=* -o buildings_parts.opl --overwrite && osmium export buildings_parts.opl -o buildings_parts.json --overwrite

# 8. COMMERCES ET POI
osmium tags-filter brussels_capital_region-latest.osm.pbf nwr/shop=* nwr/amenity=restaurant,cafe,bar,pub,museum,theatre -o poi.opl --overwrite && osmium export poi.opl -o poi.json --overwrite

# 9. ACCESSIBILITÉ
# osmium tags-filter brussels_capital_region-latest.osm.pbf nwr/wheelchair=yes,limited,no n/kerb=* -o accessibility.opl --overwrite && osmium export accessibility.opl -o accessibility.json --overwrite

# 10. OCCUPATION DES SOLS (Landuse)
osmium tags-filter brussels_capital_region-latest.osm.pbf nwr/landuse=* -o landuse.opl --overwrite && osmium export landuse.opl -o landuse.json --overwrite

# 11. RÉSEAU ROUTIER
osmium tags-filter brussels_capital_region-latest.osm.pbf nwr/highway=motorway,motorway_link,trunk,trunk_link,primary,primary_link,secondary,secondary_link,tertiary,tertiary_link,unclassified,residential,service,living_street -o roads.opl --overwrite && osmium export roads.opl -o roads.json --overwrite

# 12. WATER
osmium tags-filter brussels_capital_region-latest.osm.pbf nwr/natural=water nwr/waterway=* -o water.opl --overwrite && osmium export water.opl -o water.json --overwrite

# 13.RAIL(way)
osmium tags-filter brussels_capital_region-latest.osm.pbf nwr/railway=rail,tram,subway,station -o railways.opl --overwrite && osmium export railways.opl -o railways.json --overwrite

# 14.LIMITES ADMIN
osmium tags-filter brussels_capital_region-latest.osm.pbf nwr/boundary=administrative -o boundaries.opl --overwrite && osmium export boundaries.opl -o boundaries.json --overwrite




