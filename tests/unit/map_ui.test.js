/**
 * tests/unit/map_ui.test.js
 * ─────────────────────────
 * Tests unitaires de www/map_ui.js.
 * Importe le VRAI module — plus de copie de fonctions.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import {
  togglePanel,
  updateOsmLink,
  escapeHtml,
  buildDataPopupHtml,
} from '../../www/map_ui.js';

// ══════════════════════════════════════════════════════════
// togglePanel
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

// ══════════════════════════════════════════════════════════
// updateOsmLink
// ══════════════════════════════════════════════════════════

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

// ══════════════════════════════════════════════════════════
// escapeHtml
// ══════════════════════════════════════════════════════════

describe('escapeHtml', () => {
  it('échappe les balises HTML', () => {
    expect(escapeHtml('<script>alert("xss")</script>')).not.toContain('<script>');
    expect(escapeHtml('<b>bold</b>')).toBe('&lt;b&gt;bold&lt;/b&gt;');
  });

  it('échappe les guillemets et esperluettes', () => {
    expect(escapeHtml('a & b')).toBe('a &amp; b');
  });

  it('laisse passer le texte normal', () => {
    expect(escapeHtml('hello world')).toBe('hello world');
  });

  it('gère les chaînes vides', () => {
    expect(escapeHtml('')).toBe('');
  });
});

// ══════════════════════════════════════════════════════════
// buildDataPopupHtml
// ══════════════════════════════════════════════════════════

describe('buildDataPopupHtml', () => {
  it('affiche le layer ID et le source layer', () => {
    const feature = {
      layer: { id: 'buildings-fill' },
      sourceLayer: 'buildings',
      properties: { height: '10' },
    };
    const html = buildDataPopupHtml(feature);
    expect(html).toContain('buildings-fill');
    expect(html).toContain('(buildings)');
  });

  it('trie les propriétés par ordre alphabétique', () => {
    const feature = {
      layer: { id: 'test' },
      sourceLayer: 'src',
      properties: { z_index: '1', amenity: 'cafe', name: 'Chez Jo' },
    };
    const html = buildDataPopupHtml(feature);
    const keys = [...html.matchAll(/<th>([^<]+)<\/th>/g)].map(m => m[1]);
    expect(keys).toEqual(['amenity', 'name', 'z_index']);
  });

  it('échappe les valeurs HTML dans les propriétés (anti-XSS)', () => {
    const feature = {
      layer: { id: 'test' },
      sourceLayer: 'src',
      properties: { name: '<img src=x onerror=alert(1)>' },
    };
    const html = buildDataPopupHtml(feature);
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
  });

  it('échappe les clés HTML dans les propriétés', () => {
    const feature = {
      layer: { id: 'test' },
      sourceLayer: 'src',
      properties: { '<script>': 'bad' },
    };
    const html = buildDataPopupHtml(feature);
    expect(html).not.toContain('<script>');
  });

  it('échappe aussi le layer ID et sourceLayer', () => {
    const feature = {
      layer: { id: '<b>bad</b>' },
      sourceLayer: '<i>evil</i>',
      properties: {},
    };
    const html = buildDataPopupHtml(feature);
    expect(html).not.toContain('<b>');
    expect(html).not.toContain('<i>');
  });

  it('gère sourceLayer absent', () => {
    const feature = {
      layer: { id: 'test' },
      properties: { a: '1' },
    };
    const html = buildDataPopupHtml(feature);
    // sourceLayer || '' → chaîne vide
    expect(html).toContain('test ()');
  });
});
