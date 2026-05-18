#!/usr/bin/env node
/**
 * tests/validate-style.mjs
 * ────────────────────────
 * Validation croisée style.json ↔ PMTiles ↔ assets.
 *
 * Vérifie ce que ni les schemas JSON, ni les tests unitaires,
 * ni les E2E ne peuvent attraper :
 *
 *   1. Chaque source vectorielle pointe vers un .pmtiles.gz qui existe
 *   2. Chaque source-layer utilisé par un layer existe dans les
 *      vector_layers du PMTiles correspondant
 *   3. Chaque layer référence une source déclarée dans sources
 *   4. Pas de sources orphelines (déclarées mais jamais utilisées)
 *   5. style.json et poi-icons.json sont du JSON valide
 *   6. Chaque icône locale dans poi-icons.json existe en SVG
 *   7. Les SVG de sport markings sont présents
 *   8. Pas d'IDs de layers dupliqués
 *
 * Usage :
 *   node tests/validate-style.mjs [--www ./www]
 *
 * Exit code :
 *   0 = tout OK (avec ou sans warnings)
 *   1 = erreurs (la carte sera cassée)
 */

import fs from 'fs';
import path from 'path';
import zlib from 'zlib';

// ── Config ──────────────────────────────────────────────
const args = process.argv.slice(2);
const wwwIdx = args.indexOf('--www');
const WWW = wwwIdx >= 0 ? args[wwwIdx + 1] : './www';

const STYLE_PATH = path.join(WWW, 'style.json');
const POI_ICONS_PATH = path.join(WWW, 'poi-icons.json');
const ICONS_DIR = path.join(WWW, 'assets', 'icons');

let errors = 0;
let warnings = 0;

function error(msg) { errors++; console.error(`  ❌ ${msg}`); }
function warn(msg) { warnings++; console.warn(`  ⚠️  ${msg}`); }
function ok(msg) { console.log(`  ✅ ${msg}`); }
function section(title) { console.log(`\n── ${title} ──`); }

// ══════════════════════════════════════════════════════════
// 1. Lecture et validation JSON
// ══════════════════════════════════════════════════════════

section('Validation JSON');

let style;
try {
  const raw = fs.readFileSync(STYLE_PATH, 'utf-8');
  style = JSON.parse(raw);
  ok(`style.json valide (${(raw.length / 1024).toFixed(0)} ko)`);
} catch (e) {
  error(`style.json invalide : ${e.message}`);
  process.exit(1);
}

if (style.version !== 8) {
  error(`style.version = ${style.version}, attendu 8`);
}

let poiIcons = null;
try {
  if (fs.existsSync(POI_ICONS_PATH)) {
    const raw = fs.readFileSync(POI_ICONS_PATH, 'utf-8');
    poiIcons = JSON.parse(raw);
    const typeCount = Object.keys(poiIcons).filter(k => k !== '_meta').length;
    ok(`poi-icons.json valide (${typeCount} types)`);
  } else {
    warn('poi-icons.json absent');
  }
} catch (e) {
  error(`poi-icons.json invalide : ${e.message}`);
}

// ══════════════════════════════════════════════════════════
// 2. Lecteur de métadonnées PMTiles v3
// ══════════════════════════════════════════════════════════

/**
 * Lit le header PMTiles v3 et retourne les métadonnées JSON.
 * Spec : github.com/protomaps/PMTiles/blob/main/spec/v3/spec.md
 *
 * Header layout (127 octets, little-endian) :
 *   0x00  7B  magic "PMTiles"
 *   0x07  1B  version (3)
 *   0x08  8B  root_dir_offset
 *   0x10  8B  root_dir_length
 *   0x18  8B  metadata_offset
 *   0x20  8B  metadata_length
 *   ...
 *   0x61  1B  internal_compression (0=unknown, 1=none, 2=gzip, 3=brotli, 4=zstd)
 */
function readPMTilesMetadata(filePath) {
  const fd = fs.openSync(filePath, 'r');
  try {
    const header = Buffer.alloc(127);
    fs.readSync(fd, header, 0, 127, 0);

    const magic = header.subarray(0, 7).toString('ascii');
    if (magic !== 'PMTiles') {
      throw new Error(`magic invalide: "${magic}"`);
    }

    const version = header.readUInt8(7);
    if (version !== 3) {
      throw new Error(`version ${version}, attendu 3`);
    }

    const metaOffset = Number(header.readBigUInt64LE(24));
    const metaLength = Number(header.readBigUInt64LE(32));

    if (metaLength === 0) {
      return {};
    }

    const internalCompression = header.readUInt8(97);

    const metaBuf = Buffer.alloc(metaLength);
    fs.readSync(fd, metaBuf, 0, metaLength, metaOffset);

    let jsonStr;
    if (internalCompression === 2) {
      jsonStr = zlib.gunzipSync(metaBuf).toString('utf-8');
    } else if (internalCompression === 3) {
      jsonStr = zlib.brotliDecompressSync(metaBuf).toString('utf-8');
    } else {
      // none ou unknown — essayer tel quel, puis gzip en fallback
      try {
        jsonStr = metaBuf.toString('utf-8');
        JSON.parse(jsonStr);
      } catch {
        try {
          jsonStr = zlib.gunzipSync(metaBuf).toString('utf-8');
        } catch {
          jsonStr = metaBuf.toString('utf-8');
        }
      }
    }

    return JSON.parse(jsonStr);
  } finally {
    fs.closeSync(fd);
  }
}

// ══════════════════════════════════════════════════════════
// 3. Sources → fichiers PMTiles
// ══════════════════════════════════════════════════════════

section('Sources → fichiers PMTiles');

const sources = style.sources || {};
const sourceVectorLayers = {}; // sourceName → Set<string> | null
const sourceNames = new Set(Object.keys(sources));

for (const [name, src] of Object.entries(sources)) {
  if (src.type !== 'vector') {
    ok(`${name} : type "${src.type}" (non vérifié)`);
    continue;
  }

  if (!src.url) {
    error(`source "${name}" : pas de champ url`);
    continue;
  }

  const fileName = path.basename(src.url);
  const filePath = path.join(WWW, fileName);

  if (!fs.existsSync(filePath)) {
    error(`source "${name}" → ${fileName} introuvable dans ${WWW}/`);
    continue;
  }

  const stat = fs.statSync(filePath);
  if (stat.size < 100) {
    error(`source "${name}" → ${fileName} trop petit (${stat.size} octets)`);
    continue;
  }

  try {
    const meta = readPMTilesMetadata(filePath);
    const vectorLayers = meta.vector_layers || [];
    const layerIds = new Set(vectorLayers.map(vl => vl.id));
    sourceVectorLayers[name] = layerIds;

    const sizeKo = (stat.size / 1024).toFixed(0);
    const vlNames = [...layerIds].join(', ') || '(aucun)';
    ok(`${name} → ${fileName} (${sizeKo} ko, vector_layers: ${vlNames})`);
  } catch (e) {
    warn(`${name} → ${fileName} : métadonnées illisibles (${e.message})`);
    sourceVectorLayers[name] = null;
  }
}

// ══════════════════════════════════════════════════════════
// 4. Layers → sources et source-layers
// ══════════════════════════════════════════════════════════

section('Layers → sources / source-layers');

const layers = style.layers || [];
const usedSources = new Set();
let layerChecked = 0;
let layerOk = 0;

for (const layer of layers) {
  if (!layer.source) continue;

  usedSources.add(layer.source);

  if (!sourceNames.has(layer.source)) {
    error(`layer "${layer.id}" : source "${layer.source}" non déclarée`);
    continue;
  }

  const sl = layer['source-layer'];
  if (!sl) {
    if (sources[layer.source]?.type === 'vector') {
      warn(`layer "${layer.id}" : pas de source-layer pour source vectorielle "${layer.source}"`);
    }
    continue;
  }

  layerChecked++;

  const knownLayers = sourceVectorLayers[layer.source];
  if (knownLayers === null || knownLayers === undefined) continue;

  if (!knownLayers.has(sl)) {
    error(`layer "${layer.id}" : source-layer "${sl}" absent du PMTiles "${layer.source}" (disponibles: ${[...knownLayers].join(', ')})`);
  } else {
    layerOk++;
  }
}

ok(`${layerOk}/${layerChecked} source-layers vérifiés`);

// ══════════════════════════════════════════════════════════
// 5. Sources orphelines
// ══════════════════════════════════════════════════════════

section('Sources orphelines');

const orphans = [...sourceNames].filter(s => !usedSources.has(s));
if (orphans.length === 0) {
  ok('Aucune source orpheline');
} else {
  for (const name of orphans) {
    warn(`source "${name}" déclarée mais jamais utilisée`);
  }
}

// ══════════════════════════════════════════════════════════
// 6. Icônes POI
// ══════════════════════════════════════════════════════════

section('Icônes POI');

if (poiIcons) {
  let checked = 0;
  let found = 0;
  let missing = 0;

  for (const [type, srcs] of Object.entries(poiIcons)) {
    if (type === '_meta' || !Array.isArray(srcs)) continue;

    const localName = srcs[0];
    if (localName === null) continue;

    checked++;
    const svgPath = path.join(ICONS_DIR, `${localName}.svg`);
    const altPath = path.join(ICONS_DIR, `${localName.replace(/-/g, '_')}.svg`);

    if (fs.existsSync(svgPath) || fs.existsSync(altPath)) {
      found++;
    } else {
      missing++;
      // Ne warn que les plus importants — les icônes CDN font le fallback
      const hasCdn = srcs.slice(1).some(s => s !== null);
      if (!hasCdn) {
        warn(`"${localName}.svg" absent et aucun fallback CDN`);
      }
    }
  }

  ok(`${found}/${checked} icônes locales présentes${missing > 0 ? ` (${missing} manquantes, CDN en fallback)` : ''}`);
}

// ══════════════════════════════════════════════════════════
// 7. Sport markings SVG
// ══════════════════════════════════════════════════════════

section('Sport markings');

const SPORT_MARKINGS = [
  'sport-markings-tennis',
  'sport-markings-soccer',
  'sport-markings-basketball',
  'sport-markings-boules',
];

for (const name of SPORT_MARKINGS) {
  const svgPath = path.join(ICONS_DIR, `${name}.svg`);
  if (fs.existsSync(svgPath)) {
    ok(`${name}.svg`);
  } else {
    warn(`${name}.svg absent`);
  }
}

// ══════════════════════════════════════════════════════════
// 8. IDs de layers uniques
// ══════════════════════════════════════════════════════════

section('Unicité des IDs');

const layerIds = layers.map(l => l.id);
const duplicates = layerIds.filter((id, i) => layerIds.indexOf(id) !== i);
if (duplicates.length === 0) {
  ok(`${layerIds.length} layers, IDs uniques`);
} else {
  for (const dup of [...new Set(duplicates)]) {
    error(`layer ID "${dup}" dupliqué`);
  }
}

// ══════════════════════════════════════════════════════════
// Résumé
// ══════════════════════════════════════════════════════════

section('Résumé');
console.log(`  ${errors} erreur${errors !== 1 ? 's' : ''}, ${warnings} warning${warnings !== 1 ? 's' : ''}`);

if (errors > 0) {
  console.log('\n💥 Validation échouée — la carte sera probablement cassée.\n');
  process.exit(1);
} else if (warnings > 0) {
  console.log('\n⚠️  Validation OK avec warnings.\n');
  process.exit(0);
} else {
  console.log('\n✅ Tout est cohérent.\n');
  process.exit(0);
}
