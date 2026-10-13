import { describe, it, expect, vi } from 'vitest';
import fs from 'fs';
import path from 'path';
import {
  levelValues, levelWindow, levelFilter, indoorPaint, buildingsState,
  indoorNote, lazyLayersOf, ensureLazyGroup,
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

  it('sélection : décalage seulement si un niveau négatif est choisi', () => {
    expect(levelWindow('select', new Set([1, 2]), available)).toEqual({ lo: 1, hi: 2, offset: 0 });
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
    expect(map.addLayer.mock.calls.map(c => c[0].id)).toEqual(['indoor-3d-floor', 'indoor-3d-volume']);
    expect(map.addLayer.mock.calls.every(c => c[1] === lazy.before)).toBe(true);
  });
});
