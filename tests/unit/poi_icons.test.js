/**
 * tests/unit/poi_icons.test.js
 * ────────────────────────────
 * Tests unitaires de www/poi_icons.js.
 * Importe le VRAI module.
 */
import { describe, it, expect, vi } from 'vitest';
import {
  ICON_COLOR,
  ICON_SIZE,
  LOCAL,
  TEMAKI,
  MAKI,
  LIBERTY,
  buildIconImageExpression,
  loadPoiIcon,
} from '../../www/poi_icons.js';

// ══════════════════════════════════════════════════════════
// Constantes
// ══════════════════════════════════════════════════════════

describe('Constantes POI', () => {
  it('ICON_COLOR est un code couleur hex', () => {
    expect(ICON_COLOR).toMatch(/^#[0-9a-fA-F]{6}$/);
  });

  it('ICON_SIZE est un nombre positif', () => {
    expect(ICON_SIZE).toBeGreaterThan(0);
  });

  it('les URLs CDN sont définies', () => {
    expect(LOCAL).toBeDefined();
    expect(TEMAKI).toContain('temaki');
    expect(MAKI).toContain('maki');
    expect(LIBERTY).toContain('liberty');
  });
});

// ══════════════════════════════════════════════════════════
// buildIconImageExpression
// ══════════════════════════════════════════════════════════

describe('buildIconImageExpression', () => {
  it('retourne un coalesce minimal sans meta', () => {
    const expr = buildIconImageExpression({});
    expect(expr[0]).toBe('coalesce');
    const last = expr[expr.length - 1];
    expect(last[0]).toBe('case');
    expect(last[1]).toEqual(['has', 'shop']);
  });

  it('inclut les type_keys comme branches image/concat', () => {
    const expr = buildIconImageExpression({
      type_keys: ['amenity', 'shop', 'tourism'],
      special_cases: [],
    });

    const concatBranches = expr.filter(
      e => Array.isArray(e) && e[0] === 'image' && Array.isArray(e[1]) && e[1][0] === 'concat'
    );
    expect(concatBranches).toHaveLength(3);
    expect(concatBranches[0]).toEqual(['image', ['concat', 'poi-', ['get', 'amenity']]]);
    expect(concatBranches[1]).toEqual(['image', ['concat', 'poi-', ['get', 'shop']]]);
    expect(concatBranches[2]).toEqual(['image', ['concat', 'poi-', ['get', 'tourism']]]);
  });

  it('inclut les special_cases avant les type_keys', () => {
    const expr = buildIconImageExpression({
      type_keys: ['amenity'],
      special_cases: [
        { key: 'cuisine', value: 'friture', icon_key: 'cuisine-friture' },
      ],
    });

    expect(expr[1][0]).toBe('case');
    expect(expr[1][1]).toEqual(['==', ['get', 'cuisine'], 'friture']);
    expect(expr[1][2]).toEqual(['image', 'poi-cuisine-friture']);
    expect(expr[2]).toEqual(['image', ['concat', 'poi-', ['get', 'amenity']]]);
  });

  it('gère plusieurs special_cases', () => {
    const expr = buildIconImageExpression({
      type_keys: [],
      special_cases: [
        { key: 'cuisine', value: 'friture', icon_key: 'cuisine-friture' },
        { key: 'religion', value: 'muslim', icon_key: 'religion-muslim' },
      ],
    });

    // coalesce + 2 sc + 1 fallback = 4
    expect(expr).toHaveLength(4);
  });

  it('le fallback shop est toujours la dernière branche', () => {
    const expr = buildIconImageExpression({
      type_keys: ['amenity', 'tourism'],
      special_cases: [{ key: 'cuisine', value: 'friture', icon_key: 'cuisine-friture' }],
    });

    const last = expr[expr.length - 1];
    expect(last).toEqual([
      'case',
      ['has', 'shop'],
      ['image', 'poi-shop'],
      ['image', ''],
    ]);
  });

  it('gère meta undefined / null', () => {
    const expr1 = buildIconImageExpression({ type_keys: undefined, special_cases: undefined });
    expect(expr1[0]).toBe('coalesce');
    expect(expr1).toHaveLength(2); // coalesce + fallback

    const expr2 = buildIconImageExpression({ type_keys: null, special_cases: null });
    expect(expr2[0]).toBe('coalesce');
  });
});

// ══════════════════════════════════════════════════════════
// loadPoiIcon
// ══════════════════════════════════════════════════════════

describe('loadPoiIcon', () => {
  it('retourne false si aucune source n\'est fournie', async () => {
    const map = { addImage: vi.fn() };
    const result = await loadPoiIcon(map, 'test', null, null, null, null);
    expect(result).toBe(false);
    expect(map.addImage).not.toHaveBeenCalled();
  });

  it('essaie les URLs dans l\'ordre local → temaki → maki → liberty', async () => {
    const fetchedUrls = [];
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (url) => {
      fetchedUrls.push(url);
      return { ok: false };
    });

    const map = { addImage: vi.fn() };
    await loadPoiIcon(map, 'cafe', 'cafe', 'cafe', 'cafe', 'cafe');

    expect(fetchedUrls[0]).toContain('./assets/icons/');
    expect(fetchedUrls[1]).toContain('temaki');
    expect(fetchedUrls[2]).toContain('maki');
    expect(fetchedUrls[3]).toContain('liberty');

    globalThis.fetch = originalFetch;
  });

  it('saute les sources null', async () => {
    const fetchedUrls = [];
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (url) => {
      fetchedUrls.push(url);
      return { ok: false };
    });

    const map = { addImage: vi.fn() };
    await loadPoiIcon(map, 'cafe', null, 'cafe-temaki', null, null);

    expect(fetchedUrls).toHaveLength(1);
    expect(fetchedUrls[0]).toContain('temaki');

    globalThis.fetch = originalFetch;
  });

  it('continue au suivant si fetch échoue', async () => {
    let callCount = 0;
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async () => {
      callCount++;
      if (callCount === 1) throw new Error('network error');
      return { ok: false };
    });

    const map = { addImage: vi.fn() };
    await loadPoiIcon(map, 'test', 'a', 'b', null, null);
    expect(callCount).toBe(2);

    globalThis.fetch = originalFetch;
  });

  it('ignore les réponses non-SVG', async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      text: async () => '<html>not svg</html>',
    }));

    const map = { addImage: vi.fn() };
    const result = await loadPoiIcon(map, 'test', 'test', null, null, null);
    expect(result).toBe(false);

    globalThis.fetch = originalFetch;
  });
});
