import { test, expect } from '@playwright/test';

test.describe('ClimaSentinel Dashboard E2E', () => {
  test('should load the dashboard and display climate data', async ({ page }) => {
    // Navigate to the dashboard
    await page.goto('/');

    // Check if the main title/brand exists
    await expect(page.locator('text=ClimaSentinel').first()).toBeVisible();

    // Verify that there are no server errors or 500s showing
    const bodyText = await page.locator('body').textContent();
    expect(bodyText).not.toContain('500 Internal Server Error');

    // Check if a city card or map element loads (using a broad locator to be robust)
    // We expect at least one city name to be present on the dashboard
    const parisLocator = page.locator('text=Paris');
    await expect(parisLocator.first()).toBeVisible({ timeout: 10000 });

    // Ensure the tipping score label is present somewhere
    const scoreLocator = page.locator('text=Tipping Score');
    await expect(scoreLocator.first()).toBeVisible({ timeout: 10000 });
  });
});
