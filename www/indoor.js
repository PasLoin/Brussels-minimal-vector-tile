export const INDOOR_MODES = ['off', 'above', 'below', 'select'];

export const BUILDING_LAYERS = {
  flat: ['buildings-fill', 'buildings-outline'],
  extruded: ['buildings-3d', 'building-parts-3d'],
};

export const DIMMED_OPACITY = 0.25;

const NUM = (field) => ['to-number', ['get', field], 0];

export const ARROW_THICKNESS = 0.12;

const VALUE = (field) => (field === 'top'
  ? ['to-number', ['coalesce', ['get', 'z_top'], ['get', 'level_max']], 0]
  : NUM(field));

export function levelValues(levelsDoc) {
  const levels = (levelsDoc && Array.isArray(levelsDoc.levels)) ? levelsDoc.levels : [];
  return levels
    .map((entry) => Number(typeof entry === 'object' ? entry.level : entry))
    .filter((v) => Number.isFinite(v))
    .sort((a, b) => a - b);
}

export function levelWindow(mode, selected, available) {
  if (mode === 'above') return { lo: 0, hi: 99, offset: 0 };
  if (mode === 'below') {
    const below = (available || []).filter((v) => v < 0);
    if (!below.length) return null;
    const lo = Math.min(...below);
    return { lo, hi: Math.max(...below), offset: lo };
  }
  if (mode === 'select') {
    const values = [...(selected || [])].map(Number).filter(Number.isFinite);
    if (!values.length) return null;
    const lo = Math.min(...values);
    return { lo, hi: Math.max(...values), offset: lo };
  }
  return null;
}

export function levelFilter(mode, selected) {
  if (mode === 'above') return ['>=', NUM('level_max'), 0];
  if (mode === 'below') return ['<', NUM('level_min'), 0];
  if (mode === 'select') {
    const values = [...(selected || [])].map(Number).filter(Number.isFinite).sort((a, b) => a - b);
    if (!values.length) return ['==', 1, 0];
    return ['any', ...values.map((v) => ['all', ['<=', NUM('level_min'), v], ['>=', NUM('level_max'), v]])];
  }
  return ['==', 1, 0];
}

export function levelExpr(field, win, levelHeight) {
  const clamped = ['max', win.lo, ['min', win.hi, VALUE(field)]];
  return ['*', ['-', clamped, win.offset], levelHeight];
}

export function indoorPaint(extrusion, win, settings) {
  const h = settings.level_height;
  const top = levelExpr('top', win, h);
  if (extrusion === 'arrow') {
    const lifted = ['+', top, settings.slab];
    return {
      'fill-extrusion-base': lifted,
      'fill-extrusion-height': ['+', lifted, ARROW_THICKNESS],
    };
  }
  const extra = extrusion === 'slab'
    ? settings.slab
    : Math.round(h * settings.volume_ratio * 1000) / 1000;
  return {
    'fill-extrusion-base': levelExpr('level_min', win, h),
    'fill-extrusion-height': ['+', top, extra],
  };
}

export function buildingsState({ is3d, buildingsOn, window: win, isolated = false }) {
  const exploded = !!win && win.offset !== 0;
  const flat = buildingsOn && (!is3d || isolated);
  const extruded = buildingsOn && is3d && !exploded && !isolated;
  const visibility = {};
  for (const id of BUILDING_LAYERS.flat) visibility[id] = flat ? 'visible' : 'none';
  for (const id of BUILDING_LAYERS.extruded) visibility[id] = extruded ? 'visible' : 'none';
  return { visibility, dimmed: extruded && !!win };
}

export function indoorNote(mode, win, isolated = false) {
  if (mode === 'off') return '';
  if (!win) return mode === 'select' ? 'Cochez un ou plusieurs niveaux.' : 'Aucun niveau dans cette vue.';
  if (isolated) return `Vue isolée : le niveau ${win.lo} est posé au sol, seule l\u2019emprise des bâtiments reste affichée.`;
  if (win.offset !== 0) return `Vue éclatée : le niveau ${win.lo} est posé au sol, bâtiments 3D masqués.`;
  return 'Bâtiments 3D atténués pour voir l\u2019intérieur.';
}

export function lazyLayersOf(lazy, group) {
  return ((lazy && lazy.layers) || []).filter(
    (layer) => ((layer.metadata || {})['brussels:group']) === group,
  );
}

export function ensureLazyGroup(map, lazy, group, baseHref) {
  if (!lazy || !lazy.sources || !lazy.sources[group]) return false;
  if (map.getSource(group)) return false;
  const src = { ...lazy.sources[group] };
  if (src.url && src.url.endsWith('.pmtiles.gz')) {
    src.url = 'pmtiles://' + new URL(src.url, baseHref).href;
  }
  map.addSource(group, src);
  const before = lazy.before && map.getLayer(lazy.before) ? lazy.before : undefined;
  for (const layer of lazyLayersOf(lazy, group)) {
    map.addLayer(JSON.parse(JSON.stringify(layer)), before);
  }
  return true;
}

export function featureLevels(props) {
  const lo = Number((props || {}).level_min);
  const hi = Number((props || {}).level_max ?? lo);
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [];
  const a = Math.min(lo, hi);
  const b = Math.max(lo, hi);
  const out = new Set([a, b]);
  for (let z = Math.ceil(a); z <= Math.floor(b); z += 1) out.add(z);
  return [...out];
}

function eachCoord(coords, fn) {
  if (!Array.isArray(coords)) return;
  if (typeof coords[0] === 'number') { fn(coords); return; }
  for (const c of coords) eachCoord(c, fn);
}

export function geometryBbox(geometry) {
  let w = Infinity; let s = Infinity; let e = -Infinity; let n = -Infinity;
  eachCoord(geometry && geometry.coordinates, ([x, y]) => {
    if (x < w) w = x;
    if (x > e) e = x;
    if (y < s) s = y;
    if (y > n) n = y;
  });
  return Number.isFinite(w) ? [w, s, e, n] : null;
}

export function bboxIntersects(a, b) {
  return !!a && !!b && a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];
}

export function visibleLevels(features, bounds) {
  const out = new Set();
  for (const f of features || []) {
    if (bounds && !bboxIntersects(geometryBbox(f.geometry), bounds)) continue;
    for (const v of featureLevels(f.properties)) out.add(v);
  }
  return [...out].sort((a, b) => a - b);
}

export function sameLevels(a, b) {
  if (!a || !b || a.length !== b.length) return false;
  return a.every((v, i) => v === b[i]);
}

export function panelLevels(available, selected) {
  const present = new Set(available || []);
  const all = new Set([...present, ...[...(selected || [])].map(Number).filter(Number.isFinite)]);
  return [...all]
    .sort((a, b) => b - a)
    .map((level) => ({ level, present: present.has(level) }));
}

export function levelLabel(value) {
  if (value === 0) return '0 · rez-de-chaussée';
  return value > 0 ? `+${value}` : `${value}`;
}

export const LEVEL_AWARE_SOURCES = ['poi', 'street_furniture'];

export function poiLevelFilter(mode, selected) {
  if (mode === 'above') return ['>=', NUM('level_max'), 0];
  if (mode === 'below') return ['<', NUM('level_min'), 0];
  if (mode === 'select') {
    const values = [...(selected || [])].map(Number).filter(Number.isFinite);
    if (!values.length) return null;
    return ['all', ['!=', ['get', 'level_hint'], 'roof'], levelFilter('select', values)];
  }
  return null;
}

export function combineFilters(base, extra) {
  if (!extra) return base ?? null;
  if (!base) return extra;
  return ['all', base, extra];
}

export function levelAwareFilter(current, memo, extra) {
  const unchanged = memo && JSON.stringify(current ?? null) === JSON.stringify(memo.applied ?? null);
  const base = unchanged ? memo.base : (current ?? null);
  return { base, applied: combineFilters(base, extra) };
}

export const ISOLATION_KEEP = new Set(['background', ...BUILDING_LAYERS.flat, ...BUILDING_LAYERS.extruded]);

export function isIsolated(mode, selected, win) {
  if (!win) return false;
  if (mode === 'below') return true;
  if (mode === 'select') return ![...(selected || [])].map(Number).includes(0);
  return false;
}

export function keepsInIsolation(layer) {
  if (!layer) return false;
  if (ISOLATION_KEEP.has(layer.id)) return true;
  if (LEVEL_AWARE_SOURCES.includes(layer.source)) return true;
  const group = (layer.metadata || {})['brussels:group'];
  return group === 'indoor' || group === 'building_parts';
}
