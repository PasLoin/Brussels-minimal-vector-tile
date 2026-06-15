/**
 * poi_icons.js
 * ────────────
 * Chargement et gestion des icônes POI pour la carte Brussels.
 * Importé par index.html et par les tests unitaires.
 */

// ── Constantes ──
export const ICON_COLOR = '#734a08';
export const ICON_SIZE = 20;

// CDN bases
export const LOCAL   = './assets/icons/';
export const TEMAKI  = 'https://cdn.jsdelivr.net/npm/@ideditor/temaki@5/icons/';
export const LIBERTY = 'https://raw.githubusercontent.com/maputnik/osm-liberty/gh-pages/icons/';
export const MAKI    = 'https://cdn.jsdelivr.net/npm/@mapbox/maki/icons/';

/**
 * Normalise un SVG pour qu'il s'affiche avec ICON_COLOR,
 * quelle que soit la façon dont la couleur est définie dans la source :
 *   - attribut fill="..." / stroke="..."
 *   - style="fill:..." / style="stroke:..."
 *   - currentColor (local ou CDN bien conçus)
 *   - couleurs nommées (black, #000, #000000, rgb(0,0,0)…)
 *
 * Les valeurs "none", "transparent" et les fills structurels sont préservés.
 *
 * @param {string} svg  - Texte SVG brut
 * @param {string} color - Couleur cible (ex: '#734a08')
 * @returns {string} SVG retravaillé
 */
function recolorSvg(svg, color) {
  // 1. currentColor → couleur cible (pattern le plus propre, local et Temaki)
  svg = svg.replace(/currentColor/g, color);

  // 2. Attributs fill="..." — préserver fill="none" et fill="transparent"
  svg = svg.replace(/\bfill="(?!none|transparent)([^"]*)"/g, `fill="${color}"`);

  // 3. Attributs stroke="..." — préserver stroke="none"
  svg = svg.replace(/\bstroke="(?!none)([^"]*)"/g, `stroke="${color}"`);

  // 4. style inline : fill: ... et stroke: ... (avec ou sans espace, hex/named/rgb)
  //    Préserver fill: none et stroke: none
  svg = svg.replace(/(fill\s*:\s*)(?!none|transparent)([^;}"']+)/g, `$1${color}`);
  svg = svg.replace(/(stroke\s*:\s*)(?!none)([^;}"']+)/g,           `$1${color}`);

  // 5. Si aucun fill n'est présent sur <svg>, en ajouter un comme filet de sécurité
  if (!/<svg[^>]+\bfill=/.test(svg)) {
    svg = svg.replace(/<svg(\s|>)/i, `<svg fill="${color}" $1`);
  }

  return svg;
}

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

  for (const url of urls) {
    try {
      const res = await fetch(url);
      if (!res.ok) continue;
      let svg = await res.text();
      if (!svg.includes('<svg')) continue;

      svg = recolorSvg(svg, ICON_COLOR);

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

      const imageData = ctx.getImageData(0, 0, ICON_SIZE, ICON_SIZE);
      map.addImage('poi-' + poiType, imageData, { pixelRatio: 1 });
      return true;

    } catch (e) {
      continue;
    }
  }
  return false;
}

/**
 * Construit l'expression MapLibre icon-image à partir de _meta.
 *
 * Résultat :
 *   ["coalesce",
 *     // special cases
 *     ["case", ["==", ["get","cuisine"], "friture"], ["image","poi-cuisine-friture"], ["image",""]],
 *     // pour chaque type_key
 *     ["image", ["concat", "poi-", ["get", "shop"]]],
 *     ["image", ["concat", "poi-", ["get", "amenity"]]],
 *     // fallback
 *     ["case", ["has","shop"], ["image","poi-shop"], ["image",""]]
 *   ]
 *
 * @param {object} meta - Objet { type_keys: string[], special_cases: Array }
 * @returns {Array} Expression MapLibre GL
 */
export function buildIconImageExpression(meta) {
  const expr = ['coalesce'];

  // 1. Special cases (cuisine=friture, etc.)
  for (const sc of (meta.special_cases || [])) {
    expr.push([
      'case',
      ['==', ['get', sc.key], sc.value],
      ['image', 'poi-' + sc.icon_key],
      ['image', '']
    ]);
  }

  // 2. Chaque type_key détecté dans les données
  for (const key of (meta.type_keys || [])) {
    expr.push(['image', ['concat', 'poi-', ['get', key]]]);
  }

  // 3. Fallback : icône générique "shop"
  expr.push([
    'case',
    ['has', 'shop'],
    ['image', 'poi-shop'],
    ['image', '']
  ]);

  return expr;
}

/**
 * Charge poi-icons.json, construit l'expression icon-image,
 * puis charge toutes les icônes SVG.
 *
 * @param {object} map - MapLibre GL map instance
 */
export async function loadAllPoiIcons(map) {
  // Load military hatch pattern
  try {
    const res = await fetch('./assets/military_hatch.svg');
    const svgText = await res.text();
    const blob = new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' });
    const blobUrl = URL.createObjectURL(blob);
    const img = new Image();
    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = reject;
      img.src = blobUrl;
    });
    const size = 20;
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0, size, size);
    URL.revokeObjectURL(blobUrl);
    const imageData = ctx.getImageData(0, 0, size, size);
    if (!map.hasImage('military-hatch')) map.addImage('military-hatch', imageData, { pixelRatio: 1 });
    console.log('Military hatch pattern loaded');
  } catch (err) {
    console.error('Impossible de charger le motif militaire:', err);
  }

  // Load green hatch pattern for private parks/gardens
  try {
    const res = await fetch('./assets/military_hatch.svg');
    let svgText = await res.text();
    svgText = svgText.replace('#bd4a72', '#a9ccac');
    const blob = new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' });
    const blobUrl = URL.createObjectURL(blob);
    const img = new Image();
    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = reject;
      img.src = blobUrl;
    });
    const size = 20;
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0, size, size);
    URL.revokeObjectURL(blobUrl);
    const imageData = ctx.getImageData(0, 0, size, size);
    if (!map.hasImage('green-hatch')) map.addImage('green-hatch', imageData, { pixelRatio: 1 });
    console.log('Green hatch pattern loaded');
  } catch (err) {
    console.error('Impossible de charger le motif vert:', err);
  }

  let data;
  try {
    const resp = await fetch('./poi-icons.json');
    data = await resp.json();
  } catch (err) {
    console.error('Impossible de charger poi-icons.json:', err);
    return;
  }

  // Extraire les métadonnées et le mapping d'icônes
  const meta = data._meta || { type_keys: [], special_cases: [] };
  delete data._meta;

  // Patcher l'expression icon-image du layer poi-icon
  const iconImageExpr = buildIconImageExpression(meta);
  map.setLayoutProperty('poi-icon', 'icon-image', iconImageExpr);
  if (map.getLayer('leisure-icon')) map.setLayoutProperty('leisure-icon', 'icon-image', iconImageExpr);
  console.log('POI icon-image expression built from _meta.type_keys:', meta.type_keys);

  // Charger les icônes SVG
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
