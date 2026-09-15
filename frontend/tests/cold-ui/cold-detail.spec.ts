import { expect, test, type Locator, type Page } from '@playwright/test';

const cold = (page: Page) => page.getByRole('article', { name: /^Cold signal:/ });
const composition = (page: Page) => page.getByRole('region', { name: 'Overall score composition' });

async function expectNoTemperaturePanel(page: Page) {
  await expect(page.getByRole('region', { name: 'Cold temperature context' })).toHaveCount(0);
  for (const label of ['Forecast Tmin', 'Monthly normal Tmin', 'Below-normal anomaly']) {
    await expect(page.getByText(label, { exact: true })).toHaveCount(0);
  }
  await expect(page.getByRole('main')).not.toContainText('°C');
  await expect(page.getByRole('main')).not.toContainText('Selected score day');
}

async function expectNeutral(row: Locator, status: string) {
  await expect(row).toHaveAccessibleName(`Cold signal: ${status}`);
  await expect(row.locator('strong')).toHaveText('—');
  await expect(row).not.toHaveClass(/\brisk-/);
  // The accessible meter explains the state, but has no colored score fill.
  await expect(row.getByRole('img').locator('span')).toHaveCount(0);
  await expect(row.getByText('/ 100', { exact: true })).toHaveCount(0);
}

test('six factors include a valid measured Cold zero immediately after Heat', async ({ page }) => {
  await page.goto('/city/zero_fr');
  const rows = page.getByRole('article');
  await expect(rows).toHaveCount(6);
  await expect(rows.getByRole('heading', { level: 3 })).toHaveText([
    'Heat', 'Cold', 'Wind', 'Rain', 'Air Quality', 'River / Flood',
  ]);
  await expect(cold(page)).toHaveAccessibleName('Cold signal: Stable');
  await expect(cold(page).locator('strong')).toHaveText('0.0');
  await expect(cold(page).getByRole('img')).toHaveAccessibleName('Cold: 0.0 out of 100');
  await expect(cold(page).getByText('/ 100', { exact: true })).toBeVisible();
  await expectNoTemperaturePanel(page);
});

test('partial daily temperature coverage keeps Cold neutral without a temperature panel', async ({ page }) => {
  await page.goto('/city/partial_fr');
  await expectNeutral(cold(page), 'Unavailable');
  await expect(cold(page)).toContainText('96% daily temperature coverage');
  await expect(composition(page)).toContainText('100% aggregate coverage.');
  await expectNoTemperaturePanel(page);
});

test('a small positive Cold score remains visible instead of becoming zero', async ({ page }) => {
  await page.goto('/city/smallanomaly_fr');
  await expect(cold(page).locator('strong')).toHaveText('0.1');
  await expectNoTemperaturePanel(page);
});

test('not-monitored Cold is neutral without a score or coverage percentage', async ({ page }) => {
  await page.goto('/city/unmonitored_fr');
  await expectNeutral(cold(page), 'Not monitored');
  await expect(cold(page)).toContainText('No source configured');
  await expect(cold(page)).not.toContainText('%');
});

test('older APIs report absent Cold as unknown rather than zero', async ({ page }) => {
  await page.goto('/city/legacy_fr');
  await expectNeutral(cold(page), 'Not reported');
  await expect(cold(page)).toContainText('Cold data not reported');
  await expectNoTemperaturePanel(page);
  await expect(composition(page)).toContainText('contribution to the current tipping score is not reported');
  await expect(composition(page)).not.toContainText('shown separately');
});

test('false mode shows Cold separately without changing API score, counts or driver', async ({ page }, testInfo) => {
  await page.goto('/city/excluded_fr');
  await expect(cold(page).locator('strong')).toHaveText('100.0');
  await expect(cold(page).getByText('Dominant driver', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('article', { name: /^Wind signal:/ })).toContainText('Dominant driver');
  await expect(page.getByRole('img', { name: 'Current tipping score: 20.0 out of 100', exact: true })).toBeVisible();
  await expect(composition(page)).toContainText('5 of 5 monitored signals available for the current score.');
  await expect(composition(page)).toContainText('Cold is shown separately from the current tipping score.');
  await expect(composition(page)).toContainText('100% aggregate coverage.');
  await expectNoTemperaturePanel(page);
  await page.screenshot({ path: testInfo.outputPath('cold-desktop.png'), fullPage: true });
});

test('true mode permits Cold to drive the six-factor score', async ({ page }) => {
  await page.goto('/city/included_fr');
  await expect(cold(page)).toContainText('Dominant driver');
  await expect(page.getByRole('img', { name: 'Current tipping score: 100.0 out of 100', exact: true })).toBeVisible();
  await expect(composition(page)).toContainText('6 of 6 monitored signals available for the current score.');
  await expect(composition(page)).toContainText('Cold is included in the current tipping score when available.');
});

test('an absent mode is explicit even when Cold and aggregate counts are present', async ({ page }) => {
  await page.goto('/city/unknown_fr');
  await expect(cold(page).locator('strong')).toHaveText('100.0');
  await expect(composition(page)).toContainText('5 of 5 monitored signals available for the current score.');
  await expect(composition(page)).toContainText('contribution to the current tipping score is not reported');
  await expect(composition(page)).not.toContainText('shown separately');
});

test('unknown mode and missing API counts do not invent aggregate participation', async ({ page }) => {
  await page.goto('/city/unknowncounts_fr');
  await expect(composition(page)).toContainText('Aggregate availability not reported.');
  await expect(composition(page)).not.toContainText('6 of 6');
  await expect(composition(page)).not.toContainText('5 of 5');
});

test('false mode cannot label Cold as the dominant driver', async ({ page }) => {
  await page.goto('/city/contradictory_fr');
  await expect(cold(page).getByText('Dominant driver', { exact: true })).toHaveCount(0);
  await expect(page.locator('.city-detail-hero__metadata')).toContainText('Unknown');
});

test('available independent Cold does not create a missing five-factor aggregate', async ({ page }) => {
  await page.goto('/city/unavailableglobal_fr');
  await expect(cold(page).locator('strong')).toHaveText('100.0');
  await expect(page.getByRole('img', { name: 'Current tipping score unavailable', exact: true })).toBeVisible();
  await expect(composition(page)).toContainText('0 of 5 monitored signals available for the current score.');
  await expect(cold(page).getByText('Dominant driver', { exact: true })).toHaveCount(0);
});

test('Cold row and all six signals fit a narrow mobile viewport', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/city/partial_fr');
  await expect(page.getByRole('article')).toHaveCount(6);
  await expectNeutral(cold(page), 'Unavailable');
  await expectNoTemperaturePanel(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('cold-mobile.png'), fullPage: true });
});
