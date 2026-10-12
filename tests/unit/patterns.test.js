import { describe, it, expect, vi, afterEach } from 'vitest';
import { prepareSvg, patternUrl, loadPattern, loadPatterns } from '../../www/patterns.js';

function fakeMap(existing = []) {
  const images = new Set(existing);
  return {
    hasImage: (n) => images.has(n),
    addImage: vi.fn((n) => images.add(n)),
    triggerRepaint: vi.fn(),
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('prepareSvg', () => {
  it('remplace toutes les occurrences de chaque couleur', () => {
    const svg = '<svg><path fill="#bd4a72"/><path stroke="#bd4a72"/></svg>';
    expect(prepareSvg(svg, { '#bd4a72': '#a9ccac' }))
      .toBe('<svg><path fill="#a9ccac"/><path stroke="#a9ccac"/></svg>');
  });

  it('laisse le SVG intact sans remplacement', () => {
    expect(prepareSvg('<svg/>', undefined)).toBe('<svg/>');
  });
});

describe('patternUrl', () => {
  it('résout un chemin relatif', () => {
    expect(patternUrl('assets/patterns/x.svg')).toBe('./assets/patterns/x.svg');
    expect(patternUrl('./assets/x.svg', '/base/')).toBe('/base/assets/x.svg');
  });

  it('conserve une URL absolue', () => {
    expect(patternUrl('https://cdn.example/x.svg')).toBe('https://cdn.example/x.svg');
  });
});

describe('loadPattern', () => {
  it('ne recharge pas un motif déjà présent', async () => {
    const map = fakeMap(['military-hatch']);
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    expect(await loadPattern(map, 'military-hatch', { file: 'a.svg' })).toBe(false);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('survit à un 404 sans lever d\'erreur', async () => {
    const map = fakeMap();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: false, status: 404, text: async () => '' });
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(await loadPattern(map, 'grave_yard_generic', { file: 'x.svg', size: 32 })).toBe(false);
    expect(map.addImage).not.toHaveBeenCalled();
  });

  it('ignore une entrée sans fichier', async () => {
    expect(await loadPattern(fakeMap(), 'x', {})).toBe(false);
  });
});

describe('loadPatterns', () => {
  it('accepte une liste absente', async () => {
    vi.spyOn(console, 'log').mockImplementation(() => {});
    expect(await loadPatterns(fakeMap(), undefined)).toBe(0);
  });
});
