import { describe, it, expect, vi } from 'vitest';
import fs from 'fs';
import path from 'path';
import {
  levelValues, levelWindow, levelFilter, indoorPaint, buildingsState,
  indoorNote, lazyLayersOf, ensureLazyGroup,
  featureLevels, geometryBbox, bboxIntersects, visibleLevels, sameLevels,
  panelLevels, levelLabel,
  LEVEL_AWARE_SOURCES, poiLevelFilter, combineFilters, levelAwareFilter,
  isIsolated, keepsInIsolation,
} from '../../www/indoor.js';

const style = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../../www/style.json'), 'utf8'));
const lazy = style.metadata['brussels:lazy'];

describe('levelValues', () => {
  it('trie et filtre les niveaux', () => {
    expect(levelValues({ levels: [{ level: 1 }, { level: -2 }, { level: 'x' }, { level: 0.5 }] }))
      .toEqual([-2, 0.5, 1]);
    expect(levelValues(null)).toEqual([]);
  });
});

describe('levelWindow', () => {
  const available = [-3, -2, -1, -0.5, 0, 1, 2];

  it('au-dessus du sol : décalage nul', () => {
    expect(levelWindow('above', [], available)).toEqual({ lo: 0, hi: 99, offset: 0 });
  });

  it('souterrain : le niveau le plus bas est posé au sol', () => {
    expect(levelWindow('below', [], available)).toEqual({ lo: -3, hi: -0.5, offset: -3 });
    expect(levelWindow('below', [], [0, 1])).toBeNull();
  });

  it('sélection : le niveau le plus bas choisi est posé au sol', () => {
    expect(levelWindow('select', new Set([1, 2]), available)).toEqual({ lo: 1, hi: 2, offset: 1 });
    expect(levelWindow('select', new Set([0, 2]), available)).toEqual({ lo: 0, hi: 2, offset: 0 });
    expect(levelWindow('select', new Set([-2, 1]), available)).toEqual({ lo: -2, hi: 1, offset: -2 });
    expect(levelWindow('select', new Set(), available)).toBeNull();
  });

  it('désactivé', () => {
    expect(levelWindow('off', [], available)).toBeNull();
  });
});

describe('levelFilter', () => {
  it('sélection multiple : une clause par niveau', () => {
    const f = levelFilter('select', new Set([-1, -2]));
    expect(f[0]).toBe('any');
    expect(f).toHaveLength(3);
    expect(JSON.stringify(f[1])).toContain('-2');
  });

  it('sélection vide : rien ne passe', () => {
    expect(levelFilter('select', new Set())).toEqual(['==', 1, 0]);
  });
});

describe('cohérence avec build_map.py', () => {
  it('indoorPaint reproduit la peinture générée pour la fenêtre par défaut', () => {
    const win = { lo: 0, hi: 99, offset: 0 };
    for (const layer of lazyLayersOf(lazy, 'indoor')) {
      const extrusion = layer.metadata['brussels:extrusion'];
      const paint = indoorPaint(extrusion, win, lazy);
      expect(paint['fill-extrusion-base']).toEqual(layer.paint['fill-extrusion-base']);
      expect(paint['fill-extrusion-height']).toEqual(layer.paint['fill-extrusion-height']);
    }
  });

  it('les couches différées sont insérées sous les étiquettes', () => {
    const ids = style.layers.map(l => l.id);
    expect(ids).toContain(lazy.before);
    expect(ids.indexOf('buildings-3d')).toBeLessThan(ids.indexOf(lazy.before));
    for (const id of ['road-labels', 'poi-icon', 'public_transport-label']) {
      expect(ids.indexOf(id)).toBeGreaterThan(ids.indexOf('buildings-3d'));
    }
    for (const id of ['roads-surface-fill-primary', 'pedestrian-steps', 'cycleway']) {
      expect(ids.indexOf(id)).toBeLessThan(ids.indexOf('buildings-3d'));
    }
  });

  it('aucune couche 3D différée dans le style de base', () => {
    const ids = style.layers.map(l => l.id);
    expect(ids).not.toContain('building-parts-3d');
    expect(ids).not.toContain('indoor-3d-floor');
    expect(Object.keys(style.sources)).not.toContain('indoor');
  });
});

describe('buildingsState', () => {
  it('2D : seules les couches plates sont visibles', () => {
    const { visibility } = buildingsState({ is3d: false, buildingsOn: true, window: null });
    expect(visibility['buildings-fill']).toBe('visible');
    expect(visibility['buildings-3d']).toBe('none');
    expect(visibility['building-parts-3d']).toBe('none');
  });

  it('légende décochée puis recochée en 2D ne montre pas la 3D', () => {
    buildingsState({ is3d: false, buildingsOn: false, window: null });
    const { visibility } = buildingsState({ is3d: false, buildingsOn: true, window: null });
    expect(visibility['buildings-3d']).toBe('none');
  });

  it('3D + légende décochée : tout est masqué', () => {
    const { visibility } = buildingsState({ is3d: true, buildingsOn: false, window: null });
    expect(Object.values(visibility).every(v => v === 'none')).toBe(true);
  });

  it('vue éclatée souterraine : bâtiments 3D masqués', () => {
    const { visibility, dimmed } = buildingsState({ is3d: true, buildingsOn: true, window: { lo: -3, hi: -1, offset: -3 } });
    expect(visibility['buildings-3d']).toBe('none');
    expect(dimmed).toBe(false);
  });

  it('intérieur au-dessus du sol : bâtiments 3D atténués', () => {
    const { visibility, dimmed } = buildingsState({ is3d: true, buildingsOn: true, window: { lo: 0, hi: 99, offset: 0 } });
    expect(visibility['building-parts-3d']).toBe('visible');
    expect(dimmed).toBe(true);
  });
});

describe('indoorNote', () => {
  it('décrit la vue éclatée', () => {
    expect(indoorNote('below', { lo: -3, hi: -1, offset: -3 })).toContain('-3');
    expect(indoorNote('off', null)).toBe('');
    expect(indoorNote('select', null)).toContain('Cochez');
  });
});

describe('ensureLazyGroup', () => {
  it('ajoute la source et ses couches une seule fois, avant les étiquettes', () => {
    const sources = {};
    const layers = { [lazy.before]: {} };
    const map = {
      getSource: id => sources[id],
      getLayer: id => layers[id],
      addSource: vi.fn((id, src) => { sources[id] = src; }),
      addLayer: vi.fn((layer) => { layers[layer.id] = layer; }),
    };
    expect(ensureLazyGroup(map, lazy, 'indoor', 'https://example.org/map/')).toBe(true);
    expect(ensureLazyGroup(map, lazy, 'indoor', 'https://example.org/map/')).toBe(false);
    expect(map.addSource).toHaveBeenCalledTimes(1);
    expect(sources.indoor.url).toBe('pmtiles://https://example.org/map/indoor.pmtiles.gz');
    expect(map.addLayer.mock.calls.map(c => c[0].id)).toEqual(['indoor-3d-floor', 'indoor-3d-volume', 'indoor-3d-arrows']);
    expect(map.addLayer.mock.calls.every(c => c[1] === lazy.before)).toBe(true);
  });
});

describe('niveaux dynamiques (issue #67)', () => {
  const square = (x, y) => ({ type: 'Polygon', coordinates: [[[x, y], [x + 0.001, y], [x + 0.001, y + 0.001], [x, y + 0.001], [x, y]]] });
  const feat = (x, y, lo, hi) => ({ geometry: square(x, y), properties: { level_min: lo, level_max: hi } });

  it('featureLevels inclut les bornes et les entiers intermédiaires', () => {
    expect(featureLevels({ level_min: -2, level_max: 1 }).sort((a, b) => a - b)).toEqual([-2, -1, 0, 1]);
    expect(featureLevels({ level_min: -0.5, level_max: 0.5 }).sort((a, b) => a - b)).toEqual([-0.5, 0, 0.5]);
    expect(featureLevels({ level_min: 2 })).toEqual([2]);
    expect(featureLevels({})).toEqual([]);
  });

  it('geometryBbox et bboxIntersects', () => {
    expect(geometryBbox(square(4, 50))).toEqual([4, 50, 4.001, 50.001]);
    expect(geometryBbox(null)).toBeNull();
    expect(bboxIntersects([0, 0, 1, 1], [0.5, 0.5, 2, 2])).toBe(true);
    expect(bboxIntersects([0, 0, 1, 1], [2, 2, 3, 3])).toBe(false);
  });

  it('visibleLevels ne garde que les éléments dans la vue', () => {
    const features = [feat(4.35, 50.85, -2, -1), feat(4.35, 50.85, -2, -1), feat(5, 51, 3, 3), feat(4.351, 50.851, 0, 0)];
    expect(visibleLevels(features, [4.34, 50.84, 4.36, 50.86])).toEqual([-2, -1, 0]);
    expect(visibleLevels(features, null)).toEqual([-2, -1, 0, 3]);
    expect(visibleLevels([], [0, 0, 1, 1])).toEqual([]);
  });

  it('sameLevels compare les listes triées', () => {
    expect(sameLevels([-1, 0], [-1, 0])).toBe(true);
    expect(sameLevels([-1, 0], [0])).toBe(false);
    expect(sameLevels(null, [])).toBe(false);
  });

  it('panelLevels trie du plus haut au plus bas et garde les niveaux cochés hors vue', () => {
    expect(panelLevels([-2, -1, 0, 1, 2], new Set())).toEqual([
      { level: 2, present: true }, { level: 1, present: true }, { level: 0, present: true },
      { level: -1, present: true }, { level: -2, present: true },
    ]);
    expect(panelLevels([0, 1], new Set([-3]))).toEqual([
      { level: 1, present: true }, { level: 0, present: true }, { level: -3, present: false },
    ]);
  });

  it('levelLabel', () => {
    expect(levelLabel(0)).toContain('rez');
    expect(levelLabel(2)).toBe('+2');
    expect(levelLabel(-1.5)).toBe('-1.5');
  });
});

function evaluate(expr, props) {
  if (!Array.isArray(expr)) return expr;
  const [op, ...args] = expr;
  const ev = (e) => evaluate(e, props);
  switch (op) {
    case 'all': return args.every((a) => ev(a));
    case 'any': return args.some((a) => ev(a));
    case 'get': return props[args[0]] ?? null;
    case 'coalesce': {
      for (const a of args) { const v = ev(a); if (v !== null && v !== undefined) return v; }
      return null;
    }
    case '+': return args.reduce((acc, a) => acc + ev(a), 0);
    case '*': return args.reduce((acc, a) => acc * ev(a), 1);
    case '-': return ev(args[0]) - ev(args[1]);
    case 'max': return Math.max(...args.map(ev));
    case 'min': return Math.min(...args.map(ev));
    case 'to-number': {
      const v = ev(args[0]);
      const n = Number(v);
      return v === null || v === undefined || !Number.isFinite(n) ? ev(args[1]) : n;
    }
    case '==': return ev(args[0]) === ev(args[1]);
    case '!=': return ev(args[0]) !== ev(args[1]);
    case '<': return ev(args[0]) < ev(args[1]);
    case '<=': return ev(args[0]) <= ev(args[1]);
    case '>': return ev(args[0]) > ev(args[1]);
    case '>=': return ev(args[0]) >= ev(args[1]);
    default: throw new Error(`opérateur non géré : ${op}`);
  }
}

describe('niveaux des POI et du mobilier urbain', () => {
  const shown = (mode, selected, props) => {
    const f = poiLevelFilter(mode, new Set(selected));
    return f === null ? true : evaluate(f, props);
  };
  const rdc = {};
  const shop1 = { level_min: 1, level_max: 1 };
  const metro = { level_min: -2, level_max: -2 };
  const span = { level_min: -1, level_max: 1 };
  const roof = { level_hint: 'roof' };

  it('les sources filtrées sont poi et street_furniture', () => {
    expect(LEVEL_AWARE_SOURCES).toEqual(['poi', 'street_furniture']);
    const sources = new Set(style.layers.map((l) => l.source));
    for (const src of LEVEL_AWARE_SOURCES) expect(sources.has(src)).toBe(true);
  });

  it('un POI sans level est au rez-de-chaussée', () => {
    expect(shown('select', [0], rdc)).toBe(true);
    expect(shown('select', [1], rdc)).toBe(false);
    expect(shown('select', [-1], rdc)).toBe(false);
    expect(shown('above', [], rdc)).toBe(true);
    expect(shown('below', [], rdc)).toBe(false);
  });

  it('un POI avec level n\u2019apparaît qu\u2019à son niveau', () => {
    expect(shown('select', [1], shop1)).toBe(true);
    expect(shown('select', [0], shop1)).toBe(false);
    expect(shown('select', [-2, 1], metro)).toBe(true);
    expect(shown('below', [], metro)).toBe(true);
    expect(shown('above', [], metro)).toBe(false);
    expect(shown('select', [0], span)).toBe(true);
  });

  it('un POI sur le toit n\u2019apparaît qu\u2019au-dessus du sol', () => {
    expect(shown('above', [], roof)).toBe(true);
    expect(shown('select', [0], roof)).toBe(false);
    expect(shown('below', [], roof)).toBe(false);
  });

  it('désactivé ou sélection vide : aucun filtre ajouté', () => {
    expect(poiLevelFilter('off', new Set([1]))).toBeNull();
    expect(poiLevelFilter('select', new Set())).toBeNull();
  });

  it('combineFilters', () => {
    expect(combineFilters(null, null)).toBeNull();
    expect(combineFilters(['==', 1, 1], null)).toEqual(['==', 1, 1]);
    expect(combineFilters(null, ['==', 1, 1])).toEqual(['==', 1, 1]);
    expect(combineFilters(['==', 1, 1], ['==', 2, 2])).toEqual(['all', ['==', 1, 1], ['==', 2, 2]]);
  });

  it('levelAwareFilter retrouve le filtre de base et suit un changement externe', () => {
    const base = ['==', ['get', 'amenity'], 'bench'];
    const extra = ['>=', 1, 0];
    const first = levelAwareFilter(base, undefined, extra);
    expect(first).toEqual({ base, applied: ['all', base, extra] });
    const again = levelAwareFilter(first.applied, first, null);
    expect(again).toEqual({ base, applied: base });
    const external = ['==', ['get', 'amenity'], 'cafe'];
    expect(levelAwareFilter(external, again, extra)).toEqual({ base: external, applied: ['all', external, extra] });
  });
});

describe('vue isolée (niveau 0 non affiché)', () => {
  it('isIsolated', () => {
    const win = { lo: 1, hi: 1, offset: 1 };
    expect(isIsolated('select', new Set([1]), win)).toBe(true);
    expect(isIsolated('select', new Set([-1]), win)).toBe(true);
    expect(isIsolated('select', new Set([0, 1]), win)).toBe(false);
    expect(isIsolated('select', new Set(), null)).toBe(false);
    expect(isIsolated('below', new Set(), { lo: -2, hi: -1, offset: -2 })).toBe(true);
    expect(isIsolated('below', new Set(), null)).toBe(false);
    expect(isIsolated('above', new Set(), { lo: 0, hi: 99, offset: 0 })).toBe(false);
    expect(isIsolated('off', new Set([1]), win)).toBe(false);
  });

  it('keepsInIsolation ne garde que le fond, les bâtiments, l\u2019intérieur et les POI', () => {
    const kept = style.layers.filter((l) => keepsInIsolation(l)).map((l) => l.id);
    expect(kept).toContain('background');
    expect(kept).toContain('buildings-fill');
    expect(kept).toContain('buildings-outline');
    expect(kept).toContain('poi-icon');
    expect(kept).toContain('street-furniture-icon');
    for (const id of ['trees-tree', 'green-park', 'pitch-sport-fill', 'roads-surface-fill-primary', 'road-labels', 'leisure-icon']) {
      expect(kept).not.toContain(id);
    }
    for (const layer of lazyLayersOf(lazy, 'indoor')) expect(keepsInIsolation(layer)).toBe(true);
    expect(keepsInIsolation(null)).toBe(false);
  });

  it('buildingsState : vue isolée = emprises au sol, sans 3D', () => {
    const { visibility, dimmed } = buildingsState({ is3d: true, buildingsOn: true, window: { lo: 1, hi: 1, offset: 1 }, isolated: true });
    expect(visibility['buildings-fill']).toBe('visible');
    expect(visibility['buildings-outline']).toBe('visible');
    expect(visibility['buildings-3d']).toBe('none');
    expect(visibility['building-parts-3d']).toBe('none');
    expect(dimmed).toBe(false);
    const off = buildingsState({ is3d: true, buildingsOn: false, window: { lo: 1, hi: 1, offset: 1 }, isolated: true });
    expect(Object.values(off.visibility).every((v) => v === 'none')).toBe(true);
  });

  it('indoorNote annonce la vue isolée', () => {
    expect(indoorNote('select', { lo: 1, hi: 1, offset: 1 }, true)).toContain('Vue isolée');
    expect(indoorNote('select', { lo: 1, hi: 1, offset: 1 }, true)).toContain('1');
  });
});

describe('escaliers inclinés et flèches des escalators', () => {
  const settings = { level_height: 3, slab: 0.3, volume_ratio: 0.9 };
  const win = { lo: -2, hi: 0, offset: -2 };

  it('le dessus suit z_top quand il existe, sinon level_max', () => {
    const paint = indoorPaint('slab', win, settings);
    const height = (props) => evaluate(paint['fill-extrusion-height'], props);
    expect(height({ level_min: -2, level_max: 0 })).toBeCloseTo(6.3);
    expect(height({ level_min: -2, level_max: 0, z_top: -1.5 })).toBeCloseTo(1.8);
    expect(evaluate(paint['fill-extrusion-base'], { level_min: -2, level_max: 0, z_top: -1.5 })).toBeCloseTo(0);
  });

  it('les flèches sont posées juste au-dessus de la marche', () => {
    const paint = indoorPaint('arrow', win, settings);
    const props = { level_min: -2, level_max: 0, z_top: -1 };
    expect(evaluate(paint['fill-extrusion-base'], props)).toBeCloseTo(3.3);
    expect(evaluate(paint['fill-extrusion-height'], props)).toBeCloseTo(3.42);
  });

  it('la couche des flèches existe et ne montre que les flèches', () => {
    const arrows = lazyLayersOf(lazy, 'indoor').find((l) => l.id === 'indoor-3d-arrows');
    expect(arrows.metadata['brussels:extrusion']).toBe('arrow');
    expect(JSON.stringify(arrows.filter)).toContain('arrow');
  });
});
