import { test, expect } from '@playwright/test';

const DATA_INFO = {
  source: 'brussels_capital_region-latest.osm.pbf',
  timestamp: '2026-09-01T05:27:29Z',
  replication_timestamp: null,
  replication_sequence: null,
  sha256: 'a10eb5deacbf',
  generated_at: '2026-09-01T06:00:00Z',
};

async function openMap(page) {
  await page.goto('/');
  await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 15_000 });
}

test.describe('Attribution', () => {
  test('est dépliée et visible dès le démarrage', async ({ page }) => {
    await page.route('**/data-info.json', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DATA_INFO) })
    );
    await openMap(page);
    const attrib = page.locator('.maplibregl-ctrl-attrib');
    await expect(attrib).toBeVisible();
    await expect(attrib).not.toHaveClass(/maplibregl-compact(?!-show)/);
    const inner = page.locator('.maplibregl-ctrl-attrib-inner');
    await expect(inner).toBeVisible();
    await expect(inner).toContainText('OpenStreetMap');
    await expect(inner).toContainText('Données 01/09/2026 05:27 UTC (a10eb5deacbf)');
    await expect(inner).toContainText(/Config .*\([0-9a-f]{12}\)/);
  });

  test('affiche la config même si data-info.json est absent', async ({ page }) => {
    await page.route('**/data-info.json', (route) => route.fulfill({ status: 404, body: '' }));
    await openMap(page);
    const inner = page.locator('.maplibregl-ctrl-attrib-inner');
    await expect(inner).toBeVisible();
    await expect(inner).toContainText(/Config .*\([0-9a-f]{12}\)/);
    await expect(inner).not.toContainText('Données');
  });
});
