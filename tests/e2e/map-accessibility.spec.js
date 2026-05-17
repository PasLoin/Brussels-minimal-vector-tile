/**
 * tests/e2e/map-accessibility.spec.js
 * ────────────────────────────────────
 * Tests E2E : accessibilité, responsive, captures visuelles.
 */
import { test, expect } from '@playwright/test';

test.describe('Responsive', () => {
  test('la carte remplit tout le viewport mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });

    const canvas = page.locator('canvas.maplibregl-canvas');
    const box = await canvas.boundingBox();
    expect(box.width).toBeGreaterThanOrEqual(370);
    expect(box.height).toBeGreaterThanOrEqual(660);
  });

  test('les panneaux restent visibles sur mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });

    await expect(page.locator('#title-panel')).toBeVisible();
    await expect(page.locator('#legend-panel')).toBeVisible();
  });

  test('les boutons de contrôle sont accessibles sur mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });

    await expect(page.locator('#toggle-3d')).toBeVisible();
    await expect(page.locator('#toggle-data')).toBeVisible();
  });
});

test.describe('Captures visuelles (snapshots)', () => {
  test('capture de l\'état initial de la carte', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });
    // Attendre que les tuiles se chargent
    await page.waitForTimeout(3000);

    await expect(page).toHaveScreenshot('map-initial.png', {
      maxDiffPixelRatio: 0.05, // 5% de tolérance (tuiles réseau)
    });
  });
});

test.describe('Performance de chargement', () => {
  test('la carte se charge en moins de 10 secondes', async ({ page }) => {
    const start = Date.now();
    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 10_000 });
    const elapsed = Date.now() - start;

    expect(elapsed).toBeLessThan(10_000);
  });

  test('aucune requête réseau ne retourne 500', async ({ page }) => {
    const serverErrors = [];
    page.on('response', (resp) => {
      if (resp.status() >= 500) {
        serverErrors.push(`${resp.status()} ${resp.url()}`);
      }
    });

    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });
    await page.waitForTimeout(2000);

    expect(serverErrors).toHaveLength(0);
  });
});

test.describe('Hash URL', () => {
  test('le hash est mis à jour lors du déplacement', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });
    await page.waitForFunction(
      () => window.map && window.map.isStyleLoaded(),
      { timeout: 20_000 }
    );

    // Simuler un pan via l'API map
    await page.evaluate(() => {
      window.map.setCenter([4.36, 50.86]);
    });
    await page.waitForTimeout(500);

    const hash = await page.evaluate(() => window.location.hash);
    expect(hash).toMatch(/#\d+/); // format: #zoom/lat/lng
  });
});
