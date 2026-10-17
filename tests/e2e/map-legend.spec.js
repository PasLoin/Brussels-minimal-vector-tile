import { test, expect } from '@playwright/test';

async function waitForMapAndLegend(page) {
  await page.goto('/');
  await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });
  await page.waitForFunction(
    () => window.map && window.map.isStyleLoaded(),
    { timeout: 20_000 }
  );
  await page.waitForSelector('#legend-content .legend-row', { timeout: 10_000 });
}

async function findLegendRow(page, label) {
  const rows = page.locator('#legend-content .legend-row');
  const count = await rows.count();
  for (let i = 0; i < count; i++) {
    const text = await rows.nth(i).locator('span').textContent();
    if (text === label) return rows.nth(i);
  }
  return null;
}

async function findLegendItem(page, groupLabel, label) {
  const row = await findLegendRow(page, groupLabel);
  if (!row) return null;
  const expand = row.locator('.legend-expand');
  if (await expand.count() === 0) return null;
  if (await expand.getAttribute('aria-expanded') !== 'true') await expand.click();
  const group = row.locator('xpath=..');
  const items = group.locator('.legend-item');
  const count = await items.count();
  for (let i = 0; i < count; i++) {
    const text = await items.nth(i).locator('span').textContent();
    if (text === label) return items.nth(i);
  }
  return null;
}

async function getLayerVisibility(page, layerId) {
  return page.evaluate((id) => {
    const layer = window.map.getLayer(id);
    if (!layer) return 'not-found';
    return window.map.getLayoutProperty(id, 'visibility') || 'visible';
  }, layerId);
}

async function legendLayerIds(page) {
  return page.evaluate(() => {
    const groups = window.map.getStyle().metadata['brussels:legend'] || [];
    return groups.flatMap((g) => [...g.layers, ...g.items.flatMap((i) => i.layers)])
      .filter((id) => window.map.getLayer(id));
  });
}

test.describe('Légende : Routes masque road-labels', () => {
  test.beforeEach(async ({ page }) => {
    await waitForMapAndLegend(page);
  });

  test('cliquer Routes masque aussi le layer road-labels', async ({ page }) => {
    const row = await findLegendRow(page, 'Routes');
    test.skip(!row, 'Pas de ligne Routes dans la légende');
    if (await getLayerVisibility(page, 'road-labels') === 'not-found') {
      test.skip(true, 'Layer road-labels absent du style');
      return;
    }
    await row.click();
    expect(await getLayerVisibility(page, 'road-labels')).toBe('none');
  });

  test('re-cliquer Routes réaffiche road-labels', async ({ page }) => {
    const row = await findLegendRow(page, 'Routes');
    test.skip(!row, 'Pas de ligne Routes');
    if (await getLayerVisibility(page, 'road-labels') === 'not-found') {
      test.skip(true, 'Layer road-labels absent');
      return;
    }
    await row.click();
    await row.click();
    expect(await getLayerVisibility(page, 'road-labels')).toBe('visible');
  });
});

test.describe('Légende : couches communes du ferroviaire', () => {
  test.beforeEach(async ({ page }) => {
    await waitForMapAndLegend(page);
  });

  test('masquer Ferroviaire masque railway-bridge-casing', async ({ page }) => {
    const row = await findLegendRow(page, 'Ferroviaire');
    test.skip(!row, 'Pas de ligne Ferroviaire');
    if (await getLayerVisibility(page, 'railway-bridge-casing') === 'not-found') {
      test.skip(true, 'Layer railway-bridge-casing absent');
      return;
    }
    await row.click();
    expect(await getLayerVisibility(page, 'railway-bridge-casing')).toBe('none');
  });

  test('masquer Rail seul conserve railway-bridge-casing pour les autres modes', async ({ page }) => {
    const item = await findLegendItem(page, 'Ferroviaire', 'Rail');
    test.skip(!item, 'Pas de sous-entrée Rail');
    if (await getLayerVisibility(page, 'railway-bridge-casing') === 'not-found') {
      test.skip(true, 'Layer railway-bridge-casing absent');
      return;
    }
    await item.click();
    expect(await getLayerVisibility(page, 'railway-bridge-casing')).toBe('visible');
    const row = await findLegendRow(page, 'Ferroviaire');
    await expect(row).toHaveClass(/mixed/);
  });
});

test.describe('Légende : sous-entrées (tunnels et ponts)', () => {
  test.beforeEach(async ({ page }) => {
    await waitForMapAndLegend(page);
  });

  const cases = [
    { label: 'Rail', extras: ['railway-tunnel-rail-casing', 'railway-tunnel-rail-core', 'railway-rail-bridge-core'] },
    { label: 'Tram', extras: ['railway-tunnel-tram', 'railway-tram-bridge'] },
    { label: 'Métro', extras: ['railway-tunnel-subway', 'railway-subway-bridge'] },
  ];

  for (const { label, extras } of cases) {
    test(`cliquer ${label} masque les layers tunnel/bridge associés`, async ({ page }) => {
      const item = await findLegendItem(page, 'Ferroviaire', label);
      test.skip(!item, `Pas de sous-entrée ${label}`);
      const existing = [];
      for (const id of extras) {
        if (await getLayerVisibility(page, id) !== 'not-found') existing.push(id);
      }
      if (existing.length === 0) {
        test.skip(true, `Aucun layer tunnel/bridge pour ${label}`);
        return;
      }
      await item.click();
      await expect(item).toHaveClass(/off/);
      for (const id of existing) {
        expect(await getLayerVisibility(page, id), id).toBe('none');
      }
    });

    test(`re-cliquer ${label} réaffiche les layers tunnel/bridge`, async ({ page }) => {
      const item = await findLegendItem(page, 'Ferroviaire', label);
      test.skip(!item, `Pas de sous-entrée ${label}`);
      const existing = [];
      for (const id of extras) {
        if (await getLayerVisibility(page, id) !== 'not-found') existing.push(id);
      }
      if (existing.length === 0) {
        test.skip(true, `Aucun layer tunnel/bridge pour ${label}`);
        return;
      }
      await item.click();
      await item.click();
      for (const id of existing) {
        expect(await getLayerVisibility(page, id), id).toBe('visible');
      }
    });
  }
});

test.describe('Légende Bâtiments ↔ mode 3D', () => {
  test.beforeEach(async ({ page }) => {
    await waitForMapAndLegend(page);
  });

  test('masquer Bâtiments via légende, puis activer/désactiver 3D ne réaffiche pas buildings-fill', async ({ page }) => {
    const row = await findLegendRow(page, 'Bâtiments');
    test.skip(!row, 'Pas de ligne Bâtiments');
    if (await getLayerVisibility(page, 'buildings-fill') === 'not-found') {
      test.skip(true, 'Layer buildings-fill absent');
      return;
    }
    await row.click();
    expect(await getLayerVisibility(page, 'buildings-fill')).toBe('none');

    await page.locator('#toggle-3d').click();
    await page.waitForFunction(() => window.map && window.map.getPitch() > 10, { timeout: 5_000 });
    expect(await getLayerVisibility(page, 'buildings-fill')).toBe('none');
    expect(await getLayerVisibility(page, 'buildings-3d')).toBe('none');

    await page.locator('#toggle-3d').click();
    await page.waitForFunction(() => window.map && window.map.getPitch() < 1, { timeout: 5_000 });
    expect(await getLayerVisibility(page, 'buildings-fill')).toBe('none');
  });

  test('activer 3D puis masquer Bâtiments via légende masque buildings-3d', async ({ page }) => {
    const row = await findLegendRow(page, 'Bâtiments');
    test.skip(!row, 'Pas de ligne Bâtiments');
    await page.locator('#toggle-3d').click();
    await page.waitForFunction(() => window.map && window.map.getPitch() > 10, { timeout: 5_000 });
    await row.click();
    expect(await getLayerVisibility(page, 'buildings-fill')).toBe('none');
    const outline = await getLayerVisibility(page, 'buildings-outline');
    if (outline !== 'not-found') expect(outline).toBe('none');
    const extruded = await getLayerVisibility(page, 'buildings-3d');
    if (extruded !== 'not-found') expect(extruded).toBe('none');
  });
});

test.describe('Légende : Tout afficher / Tout masquer', () => {
  test.beforeEach(async ({ page }) => {
    await waitForMapAndLegend(page);
  });

  test('Tout masquer masque toutes les couches de la légende', async ({ page }) => {
    await page.locator('#legend-content [data-action="hide-all"]').click();
    const ids = await legendLayerIds(page);
    expect(ids.length).toBeGreaterThan(0);
    for (const id of ids) {
      expect(await getLayerVisibility(page, id), id).toBe('none');
    }
    const rows = page.locator('#legend-content .legend-row');
    await expect(rows).toHaveCount(await page.locator('#legend-content .legend-row.off').count());
  });

  test('Tout afficher réaffiche les couches 2D', async ({ page }) => {
    await page.locator('#legend-content [data-action="hide-all"]').click();
    await page.locator('#legend-content [data-action="show-all"]').click();
    const ids = (await legendLayerIds(page)).filter((id) => !id.endsWith('-3d'));
    for (const id of ids) {
      expect(await getLayerVisibility(page, id), id).toBe('visible');
    }
    await expect(page.locator('#legend-content .legend-row.off')).toHaveCount(0);
  });
});

test.describe('Légende : construite depuis les données', () => {
  test.beforeEach(async ({ page }) => {
    await waitForMapAndLegend(page);
  });

  test('chaque couche sourcée du style est pilotée par la légende', async ({ page }) => {
    const missing = await page.evaluate(() => {
      const style = window.map.getStyle();
      const groups = style.metadata['brussels:legend'] || [];
      const covered = new Set(groups.flatMap((g) => [...g.layers, ...g.items.flatMap((i) => i.layers)]));
      return style.layers.filter((l) => l.source && !covered.has(l.id)).map((l) => l.id);
    });
    expect(missing).toEqual([]);
  });

  test('une ligne par groupe déclaré, dans l’ordre des métadonnées', async ({ page }) => {
    const expected = await page.evaluate(() => (window.map.getStyle().metadata['brussels:legend'] || []).map((g) => g.label));
    const rows = page.locator('#legend-content .legend-row span');
    expect(await rows.allTextContents()).toEqual(expected);
  });

  test('toutes les catégories avec des layers correspondants sont affichées', async ({ page }) => {
    const labels = await page.locator('#legend-content .legend-row span').allTextContents();
    for (const label of ['Bâtiments', 'Routes', 'POI', 'Loisirs', 'Mobilier urbain']) {
      expect(labels, label).toContain(label);
    }
  });

  test('chaque catégorie a un swatch avec une couleur', async ({ page }) => {
    const swatches = page.locator('#legend-content .swatch');
    const count = await swatches.count();
    for (let i = 0; i < count; i++) {
      const bg = await swatches.nth(i).evaluate((el) => el.style.background);
      expect(bg.length, `swatch ${i}`).toBeGreaterThan(0);
    }
  });
});
