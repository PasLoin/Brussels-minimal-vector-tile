/**
 * tests/unit/html_structure.test.js
 * ──────────────────────────────────
 * Valide la structure HTML de index.html :
 *   - Éléments critiques présents
 *   - Scripts et dépendances référencés
 *   - Structure de la légende et des panneaux
 */
import { describe, it, expect, beforeAll } from 'vitest';
import fs from 'fs';
import path from 'path';

let html;

beforeAll(() => {
  html = fs.readFileSync(
    path.resolve(__dirname, '../../www/index.html'),
    'utf-8'
  );
  document.documentElement.innerHTML = html;
});

describe('Structure HTML de base', () => {
  it('contient le conteneur de carte #map', () => {
    expect(html).toContain('id="map"');
  });

  it('contient le panneau titre', () => {
    expect(html).toContain('id="title-panel"');
  });

  it('contient le panneau légende', () => {
    expect(html).toContain('id="legend-panel"');
    expect(html).toContain('id="legend-content"');
  });

  it('contient les boutons de contrôle', () => {
    expect(html).toContain('id="toggle-3d"');
    expect(html).toContain('id="toggle-data"');
  });

  it('contient le lien d\'édition OSM', () => {
    expect(html).toContain('id="osm-edit"');
  });
});

describe('Dépendances externes', () => {
  it('charge MapLibre GL JS', () => {
    expect(html).toContain('maplibre-gl');
    expect(html).toMatch(/maplibre-gl@[\d.]+\/dist\/maplibre-gl\.js/);
    expect(html).toMatch(/maplibre-gl@[\d.]+\/dist\/maplibre-gl\.css/);
  });

  it('charge PMTiles', () => {
    expect(html).toContain('pmtiles');
    expect(html).toMatch(/pmtiles@[\d.]+\/dist\/pmtiles\.js/);
  });

  it('charge le module sport markings', () => {
    expect(html).toContain('load_sport_markings.js');
  });
});

describe('Configuration de la carte', () => {
  it('centre sur Bruxelles par défaut', () => {
    expect(html).toContain('4.3517');
    expect(html).toContain('50.8503');
  });

  it('a un zoom initial de 13', () => {
    expect(html).toMatch(/zoom:\s*13/);
  });

  it('charge style.json', () => {
    expect(html).toContain("fetch('./style.json')");
  });

  it('référence le chargement des POI', () => {
    // Vérifie que le script importe le module POI
    expect(html).toContain('poi_icons.js');
  });
});

describe('Architecture modulaire', () => {
  it('utilise script type=module', () => {
    expect(html).toContain('type="module"');
  });

  it('importe map_ui.js', () => {
    expect(html).toContain("from './map_ui.js'");
  });

  it('importe poi_icons.js', () => {
    expect(html).toContain("from './poi_icons.js'");
  });

  it('les modules existent sur le disque', () => {
    const fs = require('fs');
    const path = require('path');
    expect(fs.existsSync(path.resolve(__dirname, '../../www/map_ui.js'))).toBe(true);
    expect(fs.existsSync(path.resolve(__dirname, '../../www/poi_icons.js'))).toBe(true);
    expect(fs.existsSync(path.resolve(__dirname, '../../www/load_sport_markings.js'))).toBe(true);
  });
});

describe('Catégories de la légende', () => {
  it('déclare les catégories attendues dans le script', () => {
    const expectedLabels = [
      'Résidentiel', 'Industriel', 'Commercial', 'Éducation',
      'Forêt', 'Parcs', 'Pelouse', 'Eau', 'Bâtiments',
      'Rail', 'Tram', 'Métro', 'Routes', 'Piétons', 'Cyclable',
      'POI', 'Limites',
    ];
    for (const label of expectedLabels) {
      expect(html).toContain(label);
    }
  });
});

describe('Styles CSS critiques', () => {
  it('définit le style du conteneur carte en plein écran', () => {
    expect(html).toMatch(/#map\s*\{[^}]*position:\s*absolute/);
    expect(html).toMatch(/#map\s*\{[^}]*inset:\s*0/);
  });

  it('définit le style du popup data', () => {
    expect(html).toContain('.data-popup');
  });

  it('gère l\'état collapsed des panneaux', () => {
    expect(html).toContain('.collapsed .panel-content');
  });
});
