/**
 * tests/e2e/map-load.spec.js
 * ──────────────────────────
 * Tests E2E : chargement de la carte, panneaux, contrôles de base.
 */
import { test, expect } from '@playwright/test';

test.describe('Chargement de la carte', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Attendre que le canvas MapLibre soit rendu
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });
  });

  test('la page se charge sans erreur console critique', async ({ page }) => {
    const errors = [];
    page.on('pageerror', (err) => errors.push(err.message));

    // Recharger pour capturer les erreurs dès le début
    await page.reload();
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });

    // Filtrer : ignorer les erreurs réseau (PMTiles absents en test)
    const critical = errors.filter(
      (e) => !e.includes('pmtiles') && !e.includes('fetch') && !e.includes('404')
    );
    expect(critical).toHaveLength(0);
  });

  test('le canvas MapLibre est visible', async ({ page }) => {
    const canvas = page.locator('canvas.maplibregl-canvas');
    await expect(canvas).toBeVisible();
    // Vérifier que le canvas a des dimensions raisonnables
    const box = await canvas.boundingBox();
    expect(box.width).toBeGreaterThan(100);
    expect(box.height).toBeGreaterThan(100);
  });

  test('le titre "Bruxelles" est affiché', async ({ page }) => {
    const title = page.locator('#title-panel h1');
    await expect(title).toHaveText('Bruxelles');
  });

  test('le sous-titre mentionne OpenStreetMap', async ({ page }) => {
    const subtitle = page.locator('#title-panel p');
    await expect(subtitle).toContainText('OpenStreetMap');
  });
});

test.describe('Panneau titre', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });
  });

  test('se replie au clic sur le header', async ({ page }) => {
    const panel = page.locator('#title-panel');
    const header = panel.locator('.panel-header');
    const content = panel.locator('.panel-content');

    await expect(content).toBeVisible();
    await header.click();
    await expect(panel).toHaveClass(/collapsed/);
    // Le contenu est masqué via CSS display:none
  });

  test('se déplie au second clic', async ({ page }) => {
    const panel = page.locator('#title-panel');
    const header = panel.locator('.panel-header');

    await header.click(); // replier
    await header.click(); // déplier
    await expect(panel).not.toHaveClass(/collapsed/);
  });
});

test.describe('Panneau légende', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });
  });

  test('est présent et contient le titre "Légende"', async ({ page }) => {
    const legend = page.locator('#legend-panel h2');
    await expect(legend).toHaveText('Légende');
  });

  test('se replie et se déplie', async ({ page }) => {
    const panel = page.locator('#legend-panel');
    const header = panel.locator('.panel-header');

    await header.click();
    await expect(panel).toHaveClass(/collapsed/);

    await header.click();
    await expect(panel).not.toHaveClass(/collapsed/);
  });
});

test.describe('Contrôles de vue', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });
  });

  test('le bouton 3D est présent et affiche "MODE 3D"', async ({ page }) => {
    const btn = page.locator('#toggle-3d');
    await expect(btn).toHaveText('MODE 3D');
  });

  test('le bouton DATA est présent', async ({ page }) => {
    const btn = page.locator('#toggle-data');
    await expect(btn).toHaveText('DATA');
  });

  test('le bouton 3D bascule le texte en "MODE 2D" au clic', async ({ page }) => {
    const btn = page.locator('#toggle-3d');
    await btn.click();
    await expect(btn).toHaveText('MODE 2D');
  });

  test('le bouton 3D revient à "MODE 3D" au deuxième clic', async ({ page }) => {
    const btn = page.locator('#toggle-3d');
    await btn.click();
    await btn.click();
    await expect(btn).toHaveText('MODE 3D');
  });

  test('le bouton DATA active le mode data (classe active)', async ({ page }) => {
    const btn = page.locator('#toggle-data');
    await btn.click();
    await expect(btn).toHaveClass(/active/);
  });

  test('le bouton DATA change le curseur en crosshair', async ({ page }) => {
    const btn = page.locator('#toggle-data');
    await btn.click();

    const canvas = page.locator('canvas.maplibregl-canvas');
    const cursor = await canvas.evaluate((el) => el.style.cursor);
    expect(cursor).toBe('crosshair');
  });
});

test.describe('Lien OSM', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });
  });

  test('le lien d\'édition OSM est présent', async ({ page }) => {
    const link = page.locator('#osm-edit');
    await expect(link).toBeVisible();
  });

  test('le lien est désactivé au zoom initial (13)', async ({ page }) => {
    const link = page.locator('#osm-edit');
    await expect(link).toHaveClass(/disabled/);
  });
});

test.describe('Contrôles MapLibre', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });
  });

  test('le contrôle de zoom est présent', async ({ page }) => {
    const zoomIn = page.locator('.maplibregl-ctrl-zoom-in');
    await expect(zoomIn).toBeVisible();
  });

  test('le contrôle d\'échelle est présent', async ({ page }) => {
    const scale = page.locator('.maplibregl-ctrl-scale');
    await expect(scale).toBeVisible();
  });
});
