/**
 * tests/unit/load_sport_markings.test.js
 * ───────────────────────────────────────
 * Tests unitaires du module de marquages sportifs.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import fs from 'fs';
import path from 'path';
import vm from 'vm';

// ── Charger le script dans le contexte jsdom ──
// Le fichier expose des globales : SPORT_MARKINGS, setupSportMarkings, rasterizeAndAdd
const scriptContent = fs.readFileSync(
  path.resolve(__dirname, '../../www/load_sport_markings.js'),
  'utf-8'
);

function loadScript() {
  // Exécuter dans le contexte global pour que var/function soient globales
  vm.runInThisContext(scriptContent);
}

loadScript();

beforeEach(() => {
  vi.restoreAllMocks();
  loadScript();
});

describe('SPORT_MARKINGS', () => {
  it('contient les 4 sports attendus', () => {
    expect(globalThis.SPORT_MARKINGS).toBeDefined();
    expect(globalThis.SPORT_MARKINGS).toHaveLength(4);
    expect(globalThis.SPORT_MARKINGS).toContain('sport-markings-tennis');
    expect(globalThis.SPORT_MARKINGS).toContain('sport-markings-soccer');
    expect(globalThis.SPORT_MARKINGS).toContain('sport-markings-basketball');
    expect(globalThis.SPORT_MARKINGS).toContain('sport-markings-boules');
  });

  it('tous les noms commencent par sport-markings-', () => {
    for (const name of globalThis.SPORT_MARKINGS) {
      expect(name).toMatch(/^sport-markings-/);
    }
  });
});

describe('setupSportMarkings', () => {
  function createMockMap(loaded = false) {
    const listeners = {};
    return {
      _loaded: loaded,
      loaded: () => loaded,
      hasImage: vi.fn(() => false),
      addImage: vi.fn(),
      on: vi.fn((event, cb) => {
        listeners[event] = listeners[event] || [];
        listeners[event].push(cb);
      }),
      _emit: (event, data) => {
        (listeners[event] || []).forEach(cb => cb(data));
      },
    };
  }

  it('enregistre un listener styleimagemissing', () => {
    const map = createMockMap(false);
    globalThis.setupSportMarkings(map);

    expect(map.on).toHaveBeenCalledWith(
      'styleimagemissing',
      expect.any(Function)
    );
  });

  it('enregistre un listener load si la carte n\'est pas prête', () => {
    const map = createMockMap(false);
    globalThis.setupSportMarkings(map);

    const loadCalls = map.on.mock.calls.filter(([ev]) => ev === 'load');
    expect(loadCalls.length).toBe(1);
  });

  it('précharge immédiatement si la carte est déjà chargée', () => {
    const map = createMockMap(true);
    // Pour vérifier le préchargement, on surveille hasImage
    globalThis.setupSportMarkings(map);

    // hasImage est appelé pour chaque sport lors du preload
    // (via rasterizeAndAdd → premier check map.hasImage)
    expect(map.hasImage).toHaveBeenCalled();
  });

  it('utilise le basePath par défaut ./assets/icons/', () => {
    const map = createMockMap(true);
    // On mock Image pour capturer le src
    const srcs = [];
    const OrigImage = globalThis.Image;
    globalThis.Image = class {
      set src(v) { srcs.push(v); }
      get src() { return ''; }
    };

    globalThis.setupSportMarkings(map);

    globalThis.Image = OrigImage;

    for (const src of srcs) {
      expect(src).toMatch(/^\.\/assets\/icons\//);
    }
  });

  it('accepte un basePath personnalisé', () => {
    const map = createMockMap(true);
    const srcs = [];
    const OrigImage = globalThis.Image;
    globalThis.Image = class {
      set src(v) { srcs.push(v); }
      get src() { return ''; }
    };

    globalThis.setupSportMarkings(map, '/custom/path/');

    globalThis.Image = OrigImage;

    for (const src of srcs) {
      expect(src).toMatch(/^\/custom\/path\//);
    }
  });
});

describe('styleimagemissing handler', () => {
  it('ne réagit qu\'aux IDs sport-markings-*', () => {
    const listeners = {};
    const map = {
      loaded: () => false,
      hasImage: vi.fn(() => false),
      addImage: vi.fn(),
      on: vi.fn((event, cb) => {
        listeners[event] = listeners[event] || [];
        listeners[event].push(cb);
      }),
    };

    globalThis.setupSportMarkings(map);

    const handler = listeners['styleimagemissing']?.[0];
    expect(handler).toBeDefined();

    // Image non-sport → ne doit PAS déclencher de chargement
    const OrigImage = globalThis.Image;
    const srcs = [];
    globalThis.Image = class {
      set src(v) { srcs.push(v); }
      get src() { return ''; }
    };

    handler({ id: 'poi-restaurant' });
    expect(srcs).toHaveLength(0);

    handler({ id: 'sport-markings-tennis' });
    expect(srcs).toHaveLength(1);

    globalThis.Image = OrigImage;
  });
});
