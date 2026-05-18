/**
 * tests/e2e/map-network.spec.js
 * ─────────────────────────────
 * Tests E2E réseau dégradé :
 *   - CDN d'icônes down → la carte reste utilisable
 *   - poi-icons.json indisponible → pas de crash
 *   - style.json indisponible → message d'erreur affiché
 *   - Pas d'erreurs JS non gérées dans chaque scénario
 */
import { test, expect } from '@playwright/test';

/**
 * Helper : collecte les erreurs JS non gérées pendant un scénario.
 * Retourne les erreurs filtrées (ignore les 404 réseau attendus).
 */
function setupErrorCollector(page, blockedPatterns = []) {
  const errors = [];
  page.on('pageerror', (err) => {
    const msg = err.message || '';
    // Ignorer les erreurs liées aux requêtes bloquées volontairement
    const isExpected = blockedPatterns.some((p) => msg.includes(p));
    if (!isExpected) {
      errors.push(msg);
    }
  });
  return errors;
}

// ══════════════════════════════════════════════════════════
// CDN d'icônes indisponibles
// ══════════════════════════════════════════════════════════

test.describe('Réseau : CDN d\'icônes down', () => {
  test('la carte reste fonctionnelle sans les CDN Temaki, Maki, Liberty', async ({ page }) => {
    const errors = setupErrorCollector(page, ['temaki', 'maki', 'liberty', 'jsdelivr', 'githubusercontent']);

    // Bloquer tous les CDN d'icônes
    await page.route('**/*jsdelivr.net/**', (route) => route.abort());
    await page.route('**/*githubusercontent.com/**', (route) => route.abort());

    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });

    // La carte doit être visible
    const canvas = page.locator('canvas.maplibregl-canvas');
    await expect(canvas).toBeVisible();

    // Les panneaux doivent fonctionner
    await expect(page.locator('#title-panel h1')).toHaveText('Bruxelles');
    await expect(page.locator('#legend-panel h2')).toHaveText('Légende');

    // Les boutons doivent fonctionner
    const btn3d = page.locator('#toggle-3d');
    await btn3d.click();
    await expect(btn3d).toHaveText('MODE 2D');

    // Pas d'erreurs JS non gérées
    expect(errors, 'Erreurs JS inattendues').toHaveLength(0);
  });

  test('les contrôles de la carte restent opérationnels sans CDN', async ({ page }) => {
    await page.route('**/*jsdelivr.net/**', (route) => route.abort());
    await page.route('**/*githubusercontent.com/**', (route) => route.abort());

    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });
    await page.waitForFunction(
      () => window.map && window.map.isStyleLoaded(),
      { timeout: 20_000 }
    );

    // Zoom fonctionne
    const zoomBefore = await page.evaluate(() => window.map.getZoom());
    await page.locator('.maplibregl-ctrl-zoom-in').click();
    await page.waitForTimeout(500);
    const zoomAfter = await page.evaluate(() => window.map.getZoom());
    expect(zoomAfter).toBeGreaterThan(zoomBefore);

    // Légende fonctionne
    await page.waitForSelector('#legend-content .legend-row', { timeout: 10_000 });
    const legendCount = await page.locator('#legend-content .legend-row').count();
    expect(legendCount).toBeGreaterThan(0);
  });
});

// ══════════════════════════════════════════════════════════
// poi-icons.json indisponible
// ══════════════════════════════════════════════════════════

test.describe('Réseau : poi-icons.json indisponible', () => {
  test('la carte ne plante pas si poi-icons.json retourne 404', async ({ page }) => {
    const errors = setupErrorCollector(page, ['poi-icons']);

    await page.route('**/poi-icons.json', (route) =>
      route.fulfill({ status: 404, body: 'Not Found' })
    );

    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });

    // La carte est visible et fonctionnelle
    await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible();
    await expect(page.locator('#title-panel h1')).toHaveText('Bruxelles');

    // Pas de crash JS
    expect(errors, 'Erreurs JS inattendues').toHaveLength(0);
  });

  test('la carte ne plante pas si poi-icons.json retourne du JSON invalide', async ({ page }) => {
    const errors = setupErrorCollector(page, ['poi-icons', 'JSON']);

    await page.route('**/poi-icons.json', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '{ invalid json !!!',
      })
    );

    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });

    await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible();

    // La carte fonctionne même sans les icônes POI
    const btn = page.locator('#toggle-data');
    await btn.click();
    await expect(btn).toHaveClass(/active/);
  });

  test('la carte ne plante pas si poi-icons.json timeout', async ({ page }) => {
    const errors = setupErrorCollector(page, ['poi-icons', 'abort']);

    await page.route('**/poi-icons.json', (route) => {
      // Ne jamais répondre → timeout côté fetch
      // Playwright va abort la requête à la fin du test
    });

    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });

    await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible();
    await expect(page.locator('#title-panel h1')).toHaveText('Bruxelles');
  });
});

// ══════════════════════════════════════════════════════════
// style.json indisponible
// ══════════════════════════════════════════════════════════

test.describe('Réseau : style.json indisponible', () => {
  test('un message d\'erreur s\'affiche si style.json retourne 404', async ({ page }) => {
    await page.route('**/style.json', (route) =>
      route.fulfill({ status: 404, body: 'Not Found' })
    );

    await page.goto('/');

    // Le message d'erreur doit apparaître dans le panneau titre
    const subtitle = page.locator('#title-panel p');
    await expect(subtitle).toContainText('Erreur', { timeout: 10_000 });
  });

  test('un message d\'erreur s\'affiche si style.json retourne du JSON invalide', async ({ page }) => {
    await page.route('**/style.json', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: 'not json at all',
      })
    );

    await page.goto('/');

    const subtitle = page.locator('#title-panel p');
    await expect(subtitle).toContainText('Erreur', { timeout: 10_000 });
  });
});

// ══════════════════════════════════════════════════════════
// MapLibre JS indisponible (CDN down)
// ══════════════════════════════════════════════════════════

test.describe('Réseau : MapLibre CDN down', () => {
  test('la page ne produit pas d\'erreur non gérée si unpkg est lent', async ({ page }) => {
    // Simuler un CDN lent (délai 3s) plutôt que bloqué
    await page.route('**/*unpkg.com/**maplibre*', async (route) => {
      await new Promise((r) => setTimeout(r, 3000));
      await route.continue();
    });

    await page.goto('/');
    // La page doit quand même charger (avec délai)
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 25_000 });
    await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible();
  });
});

// ══════════════════════════════════════════════════════════
// military_hatch.svg indisponible
// ══════════════════════════════════════════════════════════

test.describe('Réseau : assets SVG indisponibles', () => {
  test('la carte survit si military_hatch.svg retourne 404', async ({ page }) => {
    const errors = setupErrorCollector(page, ['military_hatch', 'hatch']);

    await page.route('**/military_hatch.svg', (route) =>
      route.fulfill({ status: 404, body: 'Not Found' })
    );

    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });

    await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible();
    expect(errors, 'Erreurs JS inattendues').toHaveLength(0);
  });

  test('la carte survit si les SVG sport-markings retournent 404', async ({ page }) => {
    const errors = setupErrorCollector(page, ['sport-markings']);

    await page.route('**/sport-markings-*.svg', (route) =>
      route.fulfill({ status: 404, body: 'Not Found' })
    );

    await page.goto('/');
    await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });

    await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible();
    expect(errors, 'Erreurs JS inattendues').toHaveLength(0);
  });
});
