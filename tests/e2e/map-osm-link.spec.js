/**
 * tests/e2e/map-osm-link.spec.js
 * ───────────────────────────────
 * Tests E2E du lien « éditer dans OpenStreetMap » :
 *   - Désactivé au zoom initial (13)
 *   - Activé quand on zoome à 16+
 *   - URL correcte avec zoom/lat/lng
 *   - Mis à jour après déplacement
 */
import { test, expect } from '@playwright/test';

async function waitForMap(page) {
  await page.goto('/');
  await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });
  await page.waitForFunction(
    () => window.map && window.map.isStyleLoaded(),
    { timeout: 20_000 }
  );
}

test.describe('Lien édition OSM', () => {
  test.beforeEach(async ({ page }) => {
    await waitForMap(page);
  });

  test('désactivé au zoom initial (13)', async ({ page }) => {
    const link = page.locator('#osm-edit');
    await expect(link).toHaveClass(/disabled/);

    const href = await link.getAttribute('href');
    expect(href).toBe('#');
  });

  test('s\'active quand on zoome à 16', async ({ page }) => {
    // Zoomer programmatiquement
    await page.evaluate(() => window.map.setZoom(16));
    // Déclencher moveend/zoomend pour que updateOsmLink s'exécute
    await page.evaluate(() => window.map.fire('zoomend'));
    await page.waitForTimeout(300);

    const link = page.locator('#osm-edit');
    await expect(link).not.toHaveClass(/disabled/);

    const href = await link.getAttribute('href');
    expect(href).toContain('openstreetmap.org/edit');
  });

  test('l\'URL contient le zoom arrondi et les coordonnées', async ({ page }) => {
    await page.evaluate(() => {
      window.map.setZoom(17.4);
      window.map.setCenter([4.3517, 50.8503]);
      window.map.fire('zoomend');
    });
    await page.waitForTimeout(300);

    const href = await page.locator('#osm-edit').getAttribute('href');

    // Zoom arrondi : 17.4 → 17
    expect(href).toContain('#map=17/');
    // Coordonnées de Bruxelles
    expect(href).toMatch(/50\.850/);
    expect(href).toMatch(/4\.351/);
  });

  test('se désactive quand on dézoome sous 16', async ({ page }) => {
    // D'abord zoomer
    await page.evaluate(() => {
      window.map.setZoom(17);
      window.map.fire('zoomend');
    });
    await page.waitForTimeout(300);
    await expect(page.locator('#osm-edit')).not.toHaveClass(/disabled/);

    // Puis dézoomer
    await page.evaluate(() => {
      window.map.setZoom(14);
      window.map.fire('zoomend');
    });
    await page.waitForTimeout(300);

    await expect(page.locator('#osm-edit')).toHaveClass(/disabled/);
    const href = await page.locator('#osm-edit').getAttribute('href');
    expect(href).toBe('#');
  });

  test('se met à jour après un déplacement', async ({ page }) => {
    // Zoomer et centrer sur un point
    await page.evaluate(() => {
      window.map.setZoom(17);
      window.map.setCenter([4.3517, 50.8503]);
      window.map.fire('zoomend');
    });
    await page.waitForTimeout(300);

    const href1 = await page.locator('#osm-edit').getAttribute('href');

    // Déplacer la carte vers un autre point
    await page.evaluate(() => {
      window.map.setCenter([4.3700, 50.8400]);
      window.map.fire('moveend');
    });
    await page.waitForTimeout(300);

    const href2 = await page.locator('#osm-edit').getAttribute('href');

    // L'URL doit avoir changé
    expect(href2).not.toBe(href1);
    expect(href2).toMatch(/50\.840/);
    expect(href2).toMatch(/4\.370/);
  });

  test('le lien s\'ouvre dans un nouvel onglet', async ({ page }) => {
    const target = await page.locator('#osm-edit').getAttribute('target');
    expect(target).toBe('_blank');
  });
});
