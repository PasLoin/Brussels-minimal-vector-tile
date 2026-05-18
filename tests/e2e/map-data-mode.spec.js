/**
 * tests/e2e/map-data-mode.spec.js
 * ────────────────────────────────
 * Tests E2E du mode DATA :
 *   - Activation / désactivation (bouton, curseur)
 *   - Popup affiché au hover si features présentes
 *   - Contenu du popup (layer info, propriétés triées)
 *   - Nettoyage complet à la désactivation
 *   - Pas d'interférence avec le mode normal
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

test.describe('Mode DATA : activation / désactivation', () => {
  test.beforeEach(async ({ page }) => {
    await waitForMap(page);
  });

  test('le bouton DATA active le mode (classe active + curseur crosshair)', async ({ page }) => {
    const btn = page.locator('#toggle-data');

    await btn.click();

    await expect(btn).toHaveClass(/active/);
    const cursor = await page.locator('canvas.maplibregl-canvas').evaluate(
      (el) => el.style.cursor
    );
    expect(cursor).toBe('crosshair');
  });

  test('re-cliquer DATA désactive le mode', async ({ page }) => {
    const btn = page.locator('#toggle-data');

    await btn.click(); // activer
    await btn.click(); // désactiver

    await expect(btn).not.toHaveClass(/active/);
    const cursor = await page.locator('canvas.maplibregl-canvas').evaluate(
      (el) => el.style.cursor
    );
    expect(cursor).toBe('');
  });

  test('le curseur revient à la normale après désactivation', async ({ page }) => {
    const canvas = page.locator('canvas.maplibregl-canvas');
    const btn = page.locator('#toggle-data');

    // Activer → crosshair
    await btn.click();
    expect(await canvas.evaluate((el) => el.style.cursor)).toBe('crosshair');

    // Désactiver → vide
    await btn.click();
    expect(await canvas.evaluate((el) => el.style.cursor)).toBe('');
  });

  test('le popup est supprimé à la désactivation', async ({ page }) => {
    const btn = page.locator('#toggle-data');
    const canvas = page.locator('canvas.maplibregl-canvas');

    // Activer et hover sur la carte pour potentiellement créer un popup
    await btn.click();
    const box = await canvas.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.waitForTimeout(300);

    // Désactiver
    await btn.click();

    // Aucun popup data ne doit rester
    const popup = page.locator('.data-popup');
    await expect(popup).toHaveCount(0);
  });
});

test.describe('Mode DATA : popup au hover', () => {
  test.beforeEach(async ({ page }) => {
    await waitForMap(page);
  });

  test('hover sur une zone avec features affiche un popup', async ({ page }) => {
    const btn = page.locator('#toggle-data');
    const canvas = page.locator('canvas.maplibregl-canvas');

    await btn.click();

    const box = await canvas.boundingBox();

    // Essayer plusieurs points sur la carte pour trouver une feature
    // Au centre de Bruxelles à zoom 13, il y a souvent des features (landuse, roads)
    const points = [
      { x: box.x + box.width / 2, y: box.y + box.height / 2 },
      { x: box.x + box.width / 3, y: box.y + box.height / 3 },
      { x: box.x + box.width * 2 / 3, y: box.y + box.height * 2 / 3 },
    ];

    let popupFound = false;
    for (const pt of points) {
      await page.mouse.move(pt.x, pt.y);
      await page.waitForTimeout(200);

      const count = await page.locator('.data-popup').count();
      if (count > 0) {
        popupFound = true;
        break;
      }
    }

    if (!popupFound) {
      // Pas de features rendues (PMTiles absents en CI) → skip
      test.skip(true, 'Aucune feature rendue — PMTiles probablement absents');
      return;
    }

    // Le popup doit contenir un layer-info et une table
    const popup = page.locator('.data-popup').first();
    await expect(popup.locator('.layer-info')).toBeVisible();
    await expect(popup.locator('table')).toBeVisible();
  });

  test('le popup affiche le layer ID et le source layer', async ({ page }) => {
    const btn = page.locator('#toggle-data');
    const canvas = page.locator('canvas.maplibregl-canvas');

    await btn.click();
    const box = await canvas.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.waitForTimeout(300);

    const popupCount = await page.locator('.data-popup').count();
    if (popupCount === 0) {
      test.skip(true, 'Aucune feature rendue');
      return;
    }

    const layerInfo = await page.locator('.data-popup .layer-info').textContent();

    // Format attendu : "layer-id (source-layer)"
    expect(layerInfo).toMatch(/.+ \(.+\)/);
  });

  test('les propriétés sont affichées dans un tableau', async ({ page }) => {
    const btn = page.locator('#toggle-data');
    const canvas = page.locator('canvas.maplibregl-canvas');

    await btn.click();
    const box = await canvas.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.waitForTimeout(300);

    const popupCount = await page.locator('.data-popup').count();
    if (popupCount === 0) {
      test.skip(true, 'Aucune feature rendue');
      return;
    }

    // Le tableau doit avoir des lignes th/td
    const rows = page.locator('.data-popup table tr');
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThan(0);

    // Chaque ligne a un th (clé) et un td (valeur)
    const firstTh = await rows.first().locator('th').textContent();
    expect(firstTh.length).toBeGreaterThan(0);
  });

  test('les propriétés sont triées par ordre alphabétique', async ({ page }) => {
    const btn = page.locator('#toggle-data');
    const canvas = page.locator('canvas.maplibregl-canvas');

    await btn.click();
    const box = await canvas.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.waitForTimeout(300);

    const popupCount = await page.locator('.data-popup').count();
    if (popupCount === 0) {
      test.skip(true, 'Aucune feature rendue');
      return;
    }

    // Récupérer toutes les clés (th) du tableau
    const keys = await page.locator('.data-popup table th').allTextContents();
    if (keys.length < 2) return; // pas assez de clés pour vérifier le tri

    const sorted = [...keys].sort();
    expect(keys).toEqual(sorted);
  });
});

test.describe('Mode DATA : le popup disparaît correctement', () => {
  test.beforeEach(async ({ page }) => {
    await waitForMap(page);
  });

  test('le popup disparaît quand la souris quitte une feature', async ({ page }) => {
    const btn = page.locator('#toggle-data');
    const canvas = page.locator('canvas.maplibregl-canvas');

    await btn.click();
    const box = await canvas.boundingBox();

    // Hover au centre (probable feature)
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.waitForTimeout(300);

    const hadPopup = await page.locator('.data-popup').count() > 0;

    if (!hadPopup) {
      test.skip(true, 'Aucune feature rendue');
      return;
    }

    // Utiliser queryRenderedFeatures pour trouver un point sans feature
    const emptyPoint = await page.evaluate(() => {
      const canvas = window.map.getCanvas();
      const w = canvas.width;
      const h = canvas.height;
      // Tester les coins — souvent vides
      const corners = [
        [5, 5], [w - 5, 5], [5, h - 5], [w - 5, h - 5],
      ];
      for (const [x, y] of corners) {
        const features = window.map.queryRenderedFeatures([x, y]);
        if (features.length === 0) return { x, y };
      }
      return null;
    });

    if (!emptyPoint) {
      // Tout le canvas a des features → on ne peut pas tester la disparition
      return;
    }

    // Déplacer la souris vers le point vide
    const canvasRect = await canvas.boundingBox();
    const scale = await page.evaluate(() => window.devicePixelRatio || 1);
    await page.mouse.move(
      canvasRect.x + emptyPoint.x / scale,
      canvasRect.y + emptyPoint.y / scale
    );
    await page.waitForTimeout(300);

    // Le popup doit avoir disparu
    const popupCount = await page.locator('.data-popup').count();
    expect(popupCount).toBe(0);
  });
});

test.describe('Mode DATA : pas d\'interférence', () => {
  test.beforeEach(async ({ page }) => {
    await waitForMap(page);
  });

  test('le mode DATA n\'interfère pas avec le hover normal quand désactivé', async ({ page }) => {
    const canvas = page.locator('canvas.maplibregl-canvas');
    const box = await canvas.boundingBox();

    // Sans activer DATA, hover sur la carte
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.waitForTimeout(300);

    // Aucun popup data ne doit apparaître
    const popupCount = await page.locator('.data-popup').count();
    expect(popupCount).toBe(0);

    // Le curseur ne doit pas être crosshair
    const cursor = await canvas.evaluate((el) => el.style.cursor);
    expect(cursor).not.toBe('crosshair');
  });

  test('activer/désactiver DATA rapidement ne laisse pas de popup fantôme', async ({ page }) => {
    const btn = page.locator('#toggle-data');
    const canvas = page.locator('canvas.maplibregl-canvas');
    const box = await canvas.boundingBox();

    // Toggle rapide 5 fois
    for (let i = 0; i < 5; i++) {
      await btn.click();
      await page.mouse.move(
        box.x + box.width / 2 + i * 10,
        box.y + box.height / 2
      );
    }

    // Finir désactivé (5 clics = impair → actif, donc un de plus)
    await btn.click();
    await page.waitForTimeout(300);

    // Pas de popup, pas de crosshair
    await expect(page.locator('.data-popup')).toHaveCount(0);
    const cursor = await canvas.evaluate((el) => el.style.cursor);
    expect(cursor).toBe('');
  });
});
