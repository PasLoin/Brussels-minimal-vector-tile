tippecanoe -o brussels_ultimate_v2.pmtiles --force \
  --maximum-zoom=16 \
  --attribution="OpenStreetMap contributors" \
  --generate-ids \
  --drop-densest-as-needed \
  --extend-zooms-if-still-dropping \
  landuse.json \
  pedestrian.json \
  cycling.json \
  furniture.json \
  infra.json \
  green.json \
  buildings.json \
  buildings_parts.json \
  poi.json \
  accessibility.json
