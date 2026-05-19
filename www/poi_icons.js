/**
 * poi_icons.js
 * ────────────
 * Chargement et gestion des icônes POI pour la carte Brussels.
 * Importé par index.html et par les tests unitaires.
 */

// ── Constantes ──
const iconLoadingCache = new Map();
export const ICON_COLOR = '#734a08';
export const ICON_SIZE = 20;

// CDN bases
export const LOCAL   = './assets/icons/';
export const TEMAKI  = 'https://cdn.jsdelivr.net/npm/@ideditor/temaki@5/icons/';
export const LIBERTY = 'https://raw.githubusercontent.com/maputnik/osm-liberty/gh-pages/icons/';
export const MAKI    = 'https://cdn.jsdelivr.net/npm/@mapbox/maki/icons/';

/**
 * Fetch SVG, recolor, render to canvas, add to map.
 * Tries sources in order: local → temaki → maki → liberty
 *
 * @param {object} map - MapLibre GL map instance
 * @param {string} poiType - Type POI (ex: "restaurant")
 * @param {string|null} localName - Nom fichier local (sans .svg)
 * @param {string|null} temakiName - Nom Temaki
 * @param {string|null} makiName - Nom Maki
 * @param {string|null} libertyName - Nom OSM Liberty
 * @returns {Promise<boolean>} true si une icône a été chargée
 */
export async function loadPoiIcon(map, poiType, localName, temakiName, makiName, libertyName) {
  const urls = [];
  if (localName)   urls.push(LOCAL + localName + '.svg');
  if (temakiName)  urls.push(TEMAKI + temakiName + '.svg');
  if (makiName)    urls.push(MAKI + makiName + '.svg');
  if (libertyName) urls.push(LIBERTY + libertyName + '.svg');

  const cacheKey = JSON.stringify(urls);

  if (!iconLoadingCache.has(cacheKey)) {
    iconLoadingCache.set(cacheKey, (async () => {
      for (const url of urls) {
        try {
          const res = await fetch(url);
          if (!res.ok) continue;
          let svg = await res.text();
          if (!svg.includes('<svg')) continue;

          svg = svg.replace(/\s*fill="[^"]*"/g, '');
          svg = svg.replace(/<svg(\s|>)/i, `<svg fill="${ICON_COLOR}" $1`);

          const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
          const blobUrl = URL.createObjectURL(blob);
          const img = new Image();

          await new Promise((resolve, reject) => {
            img.onload = resolve;
            img.onerror = reject;
            img.src = blobUrl;
          });

          const canvas = document.createElement('canvas');
          canvas.width = ICON_SIZE;
          canvas.height = ICON_SIZE;
          const ctx = canvas.getContext('2d');
          ctx.drawImage(img, 0, 0, ICON_SIZE, ICON_SIZE);
          URL.revokeObjectURL(blobUrl);

          return ctx.getImageData(0, 0, ICON_SIZE, ICON_SIZE);
        } catch (e) {
          continue;
        }
      }
      return null;
    })());
  }

  const imageData = await iconLoadingCache.get(cacheKey);
  if (imageData) {
    map.addImage('poi-' + poiType, imageData, { pixelRatio: 1 });
    return true;
  }
  return false;
}

/**
 * Construit l'expression MapLibre icon-image à partir de _meta.
 *
 * @param {object} meta - Objet { type_keys: string[], special_cases: Array }
 * @returns {Array} Expression MapLibre GL
 */
export function buildIconImageExpression(meta) {
  const expr = ['coalesce'];

  for (const sc of (meta.special_cases || [])) {
    expr.push([
      'case',
      ['==', ['get', sc.key], sc.value],
      ['image', 'poi-' + sc.icon_key],
      ['image', '']
    ]);
  }

  for (const key of (meta.type_keys || [])) {
    expr.push(['image', ['concat', 'poi-', ['get', key]]]);
  }

  expr.push([
    'case',
    ['has', 'shop'],
    ['image', 'poi-shop'],
    ['image', '']
  ]);

  return expr;
}

/**
 * Charge un motif SVG hatch et l'ajoute comme image sur la carte.
 *
 * @param {object} map - MapLibre GL map instance
 * @param {string} svgPath - Chemin vers le fichier SVG
 * @param {string} imageName - Nom de l'image dans la carte
 * @param {number} [size=20] - Taille du pattern en pixels
 */
async function loadHatchPattern(map, svgPath, imageName, size = 20) {
  try {
    const res = await fetch(svgPath);
    const svgText = await res.text();
    const blob = new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' });
    const blobUrl = URL.createObjectURL(blob);
    const img = new Image();
    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = reject;
      img.src = blobUrl;
    });
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0, size, size);
    URL.revokeObjectURL(blobUrl);
    const imageData = ctx.getImageData(0, 0, size, size);
    if (!map.hasImage(imageName)) map.addImage(imageName, imageData, { pixelRatio: 1 });
    console.log(`${imageName} pattern loaded`);
  } catch (err) {
    console.error(`Impossible de charger le motif ${imageName}:`, err);
  }
}

/**
 * Charge poi-icons.json, construit l'expression icon-image,
 * puis charge toutes les icônes SVG.
 *
 * @param {object} map - MapLibre GL map instance
 */
export async function loadAllPoiIcons(map) {
  // Load hatch patterns
  await loadHatchPattern(map, './assets/military_hatch.svg', 'military-hatch');
  await loadHatchPattern(map, './assets/park_hatch.svg', 'park-hatch');

  let data;
  try {
    const resp = await fetch('./poi-icons.json');
    data = await resp.json();
  } catch (err) {
    console.error('Impossible de charger poi-icons.json:', err);
    return;
  }

  const meta = data._meta || { type_keys: [], special_cases: [] };
  delete data._meta;

  const iconImageExpr = buildIconImageExpression(meta);
  map.setLayoutProperty('poi-icon', 'icon-image', iconImageExpr);
  if (map.getLayer('leisure-icon')) map.setLayoutProperty('leisure-icon', 'icon-image', iconImageExpr);
  console.log('POI icon-image expression built from _meta.type_keys:', meta.type_keys);

  const entries = Object.entries(data);
  const results = await Promise.allSettled(
    entries.map(([type, sources]) =>
      loadPoiIcon(map, type, ...sources)
    )
  );
  const loaded = results.filter(r => r.status === 'fulfilled' && r.value).length;
  console.log(`POI icons: ${loaded}/${entries.length} loaded`);
  map.triggerRepaint();
}
