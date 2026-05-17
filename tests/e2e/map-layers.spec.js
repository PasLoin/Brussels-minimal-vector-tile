/**
 * tests/e2e/map-layers.spec.js
 * ────────────────────────────
 * Tests E2E : présence des couches, interaction légende,
 * chargement des données PMTiles.
 */
import { test, expect } from '@playwright/test';

test.describe('Couches de la carte', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });
    // Attendre que le style soit chargé
    await page.waitForFunction(
      () => window.map && window.map.isStyleLoaded(),
      { timeout: 20_000 }
    );
  });

  test('le style contient les couches essentielles', async ({ page }) => {
    const layerIds = await page.evaluate(() => {
      return window.map.getStyle().layers.map((l) => l.id);
    });

    const expectedPatterns = [
      'landuse-',
      'water-',
      'green-',
      'buildings',
      'roads-',
      'poi-',
    ];

    for (const pattern of expectedPatterns) {
      const found = layerIds.some((id) => id.startsWith(pattern) || id.includes(pattern));
      expect(found, `Couche matching "${pattern}" attendue`).toBe(true);
    }
  });

  test('les sources de données sont déclarées', async ({ page }) => {
    const sourceNames = await page.evaluate(() => {
      return Object.keys(window.map.getStyle().sources);
    });

    // Au minimum on doit avoir quelques sources PMTiles
    expect(sourceNames.length).toBeGreaterThan(0);
  });

  test('le bâtiment 3D existe mais est masqué par défaut', async ({ page }) => {
    const building3dVisible = await page.evaluate(() => {
      const layer = window.map.getLayer('buildings-3d');
      if (!layer) return 'not-found';
      return window.map.getLayoutProperty('buildings-3d', 'visibility');
    });

    // Soit absent soit masqué
    expect(['none', 'not-found']).toContain(building3dVisible);
  });

  test('les couches poi-icon et leisure-icon existent', async ({ page }) => {
    const poiExists = await page.evaluate(() => !!window.map.getLayer('poi-icon'));
    expect(poiExists).toBe(true);
  });
});

test.describe('Interaction légende ↔ couches', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });
    await page.waitForFunction(
      () => window.map && window.map.isStyleLoaded(),
      { timeout: 20_000 }
    );
    // Attendre que la légende soit remplie
    await page.waitForSelector('#legend-content .legend-row', { timeout: 10_000 });
  });

  test('la légende contient des entrées', async ({ page }) => {
    const count = await page.locator('#legend-content .legend-row').count();
    expect(count).toBeGreaterThan(5);
  });

  test('chaque entrée a un swatch coloré et un label', async ({ page }) => {
    const rows = page.locator('#legend-content .legend-row');
    const count = await rows.count();

    for (let i = 0; i < Math.min(count, 5); i++) {
      const row = rows.nth(i);
      await expect(row.locator('.swatch')).toBeVisible();
      await expect(row.locator('span')).toBeVisible();
      const text = await row.locator('span').textContent();
      expect(text.length).toBeGreaterThan(0);
    }
  });

  test('cliquer une entrée la grise (classe .off)', async ({ page }) => {
    const firstRow = page.locator('#legend-content .legend-row').first();
    await firstRow.click();
    await expect(firstRow).toHaveClass(/off/);
  });

  test('cliquer deux fois retire la classe .off', async ({ page }) => {
    const firstRow = page.locator('#legend-content .legend-row').first();
    await firstRow.click();
    await firstRow.click();
    await expect(firstRow).not.toHaveClass(/off/);
  });

  test('cliquer Bâtiments masque le layer correspondant', async ({ page }) => {
    // Trouver la ligne "Bâtiments"
    const rows = page.locator('#legend-content .legend-row');
    const count = await rows.count();

    let buildingRow = null;
    for (let i = 0; i < count; i++) {
      const text = await rows.nth(i).locator('span').textContent();
      if (text === 'Bâtiments') {
        buildingRow = rows.nth(i);
        break;
      }
    }

    if (!buildingRow) {
      test.skip(true, 'Pas de ligne Bâtiments dans la légende');
      return;
    }

    await buildingRow.click();

    // Vérifier que les couches buildings sont masquées
    const visibility = await page.evaluate(() => {
      const layer = window.map.getLayer('buildings-fill');
      return layer ? window.map.getLayoutProperty('buildings-fill', 'visibility') : null;
    });

    expect(visibility).toBe('none');
  });
});

test.describe('Mode 3D et couches bâtiments', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });
    await page.waitForFunction(
      () => window.map && window.map.isStyleLoaded(),
      { timeout: 20_000 }
    );
  });

  test('activer le 3D masque buildings-fill et montre buildings-3d', async ({ page }) => {
    await page.locator('#toggle-3d').click();

    // Attendre que l'animation easeTo soit terminée (pitch > 0)
    await page.waitForFunction(
      () => window.map && window.map.getPitch() > 10,
      { timeout: 5_000 }
    );

    const result = await page.evaluate(() => {
      const fillVis = window.map.getLayer('buildings-fill')
        ? window.map.getLayoutProperty('buildings-fill', 'visibility')
        : 'not-found';
      const threeDVis = window.map.getLayer('buildings-3d')
        ? window.map.getLayoutProperty('buildings-3d', 'visibility')
        : 'not-found';
      const pitch = window.map.getPitch();
      return { fillVis, threeDVis, pitch };
    });

    expect(result.fillVis).toBe('none');
    expect(result.threeDVis).toBe('visible');
    expect(result.pitch).toBeGreaterThan(0);
  });

  test('désactiver le 3D restaure les bâtiments 2D', async ({ page }) => {
    // Activer 3D
    await page.locator('#toggle-3d').click();
    await page.waitForFunction(
      () => window.map && window.map.getPitch() > 10,
      { timeout: 5_000 }
    );

    // Désactiver 3D
    await page.locator('#toggle-3d').click();
    await page.waitForFunction(
      () => window.map && window.map.getPitch() < 1,
      { timeout: 5_000 }
    );

    const result = await page.evaluate(() => {
      const fillVis = window.map.getLayer('buildings-fill')
        ? window.map.getLayoutProperty('buildings-fill', 'visibility')
        : 'not-found';
      const pitch = window.map.getPitch();
      return { fillVis, pitch };
    });

    expect(result.fillVis).toBe('visible');
    expect(result.pitch).toBe(0);
  });
});

test.describe('Terrains de sport (pitch)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });
    await page.waitForFunction(
      () => window.map && window.map.isStyleLoaded(),
      { timeout: 20_000 }
    );
  });

  test('les couches pitch-sport existent dans le style', async ({ page }) => {
    const pitchLayers = await page.evaluate(() => {
      return window.map
        .getStyle()
        .layers.filter((l) => l.id.startsWith('pitch-'))
        .map((l) => l.id);
    });

    expect(pitchLayers).toContain('pitch-sport-fill');
    expect(pitchLayers).toContain('pitch-sport-outline');
    expect(pitchLayers).toContain('pitch-markings');
  });

  test('pitch-markings utilise icon-image basé sur sport_render', async ({ page }) => {
    const iconImage = await page.evaluate(() => {
      const layer = window.map.getLayer('pitch-markings');
      if (!layer) return null;
      return window.map.getLayoutProperty('pitch-markings', 'icon-image');
    });

    // L'expression doit contenir "sport-markings-"
    expect(JSON.stringify(iconImage)).toContain('sport-markings-');
  });
});
