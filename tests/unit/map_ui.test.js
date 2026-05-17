/**
 * tests/unit/map_ui.test.js
 * ─────────────────────────
 * Tests unitaires des fonctions UI de la carte (inline dans index.html).
 * On les réimplémente ici pour les tester isolément.
 */
import { describe, it, expect, beforeEach } from 'vitest';

// ══════════════════════════════════════════════════════════
// Fonctions extraites de index.html (copie fidèle)
// ══════════════════════════════════════════════════════════

function togglePanel(id) {
  document.getElementById(id).classList.toggle('collapsed');
}

function updateOsmLink(map) {
  const link = document.getElementById('osm-edit');
  const zoom = map.getZoom();
  const center = map.getCenter();

  if (zoom >= 16) {
    link.classList.remove('disabled');
    link.href = `https://www.openstreetmap.org/edit#map=${Math.round(zoom)}/${center.lat.toFixed(5)}/${center.lng.toFixed(5)}`;
  } else {
    link.classList.add('disabled');
    link.href = '#';
  }
}

function buildIconImageExpression(meta) {
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

// ══════════════════════════════════════════════════════════
// Tests
// ══════════════════════════════════════════════════════════

describe('togglePanel', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="test-panel" class="panel">
        <div class="panel-content">contenu</div>
      </div>
    `;
  });

  it('ajoute la classe collapsed au premier clic', () => {
    togglePanel('test-panel');
    expect(document.getElementById('test-panel').classList.contains('collapsed')).toBe(true);
  });

  it('retire la classe collapsed au deuxième clic', () => {
    togglePanel('test-panel');
    togglePanel('test-panel');
    expect(document.getElementById('test-panel').classList.contains('collapsed')).toBe(false);
  });
});

describe('updateOsmLink', () => {
  beforeEach(() => {
    document.body.innerHTML = `<a id="osm-edit" class="osm-edit disabled" href="#">éditer</a>`;
  });

  it('active le lien quand zoom >= 16', () => {
    const map = {
      getZoom: () => 17,
      getCenter: () => ({ lat: 50.8503, lng: 4.3517 }),
    };
    updateOsmLink(map);

    const link = document.getElementById('osm-edit');
    expect(link.classList.contains('disabled')).toBe(false);
    expect(link.href).toContain('openstreetmap.org/edit');
    expect(link.href).toContain('50.85030');
    expect(link.href).toContain('4.35170');
  });

  it('désactive le lien quand zoom < 16', () => {
    const map = {
      getZoom: () => 14,
      getCenter: () => ({ lat: 50.8503, lng: 4.3517 }),
    };
    updateOsmLink(map);

    const link = document.getElementById('osm-edit');
    expect(link.classList.contains('disabled')).toBe(true);
    expect(link.href).toContain('#');
  });

  it('arrondit le zoom dans l\'URL', () => {
    const map = {
      getZoom: () => 17.6,
      getCenter: () => ({ lat: 50.0, lng: 4.0 }),
    };
    updateOsmLink(map);

    const link = document.getElementById('osm-edit');
    expect(link.href).toContain('#map=18/');
  });

  it('gère le zoom exact à 16', () => {
    const map = {
      getZoom: () => 16,
      getCenter: () => ({ lat: 50.0, lng: 4.0 }),
    };
    updateOsmLink(map);

    const link = document.getElementById('osm-edit');
    expect(link.classList.contains('disabled')).toBe(false);
  });
});

describe('buildIconImageExpression', () => {
  it('retourne un coalesce minimal sans meta', () => {
    const expr = buildIconImageExpression({});
    expect(expr[0]).toBe('coalesce');
    // Doit contenir au moins le fallback shop
    const last = expr[expr.length - 1];
    expect(last[0]).toBe('case');
    expect(last[1]).toEqual(['has', 'shop']);
  });

  it('inclut les type_keys comme branches image/concat', () => {
    const expr = buildIconImageExpression({
      type_keys: ['amenity', 'shop', 'tourism'],
      special_cases: [],
    });

    // Après le coalesce, on doit trouver 3 branches image+concat
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

    // expr[1] doit être le special case
    expect(expr[1][0]).toBe('case');
    expect(expr[1][1]).toEqual(['==', ['get', 'cuisine'], 'friture']);
    expect(expr[1][2]).toEqual(['image', 'poi-cuisine-friture']);

    // expr[2] doit être le type_key amenity
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

    // 2 special cases + 1 fallback shop = 4 éléments après 'coalesce'
    expect(expr).toHaveLength(4); // coalesce + 2 sc + 1 fallback
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
});
