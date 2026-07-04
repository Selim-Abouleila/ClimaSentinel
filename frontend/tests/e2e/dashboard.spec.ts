import { test, expect } from '@playwright/test';

test.describe('ClimaSentinel Forecast E2E', () => {
  test('should navigate to forecast page, select Paris, and display ML scoring cards', async ({ page }) => {
    // 1. Navigate to the forecast page
    await page.goto('/forecast');

    // 2. Verify the hero title loaded
    await expect(page.locator('text=AI Tipping Forecast')).toBeVisible();

    // 3. Verify there are no 500 errors
    const bodyText = await page.locator('body').textContent();
    expect(bodyText).not.toContain('500 Internal Server Error');

    // 4. Select the City
    await page.click('text=Paris, FR');

    // 5. Select the Forecast Horizon (+3 Days)
    await page.click('text=+3 Days');

    // 6. Wait for the ML Scoring Cards to render
    // The "Est. Total Risk (Day +3)" text appears when data is fetched successfully from BigQuery & ML Model
    const riskLabel = page.locator('text=Est. Total Risk');
    await expect(riskLabel.first()).toBeVisible({ timeout: 15000 });

    // 7. Validate that granular sub-scores loaded
    const heatScoreLabel = page.locator('text=Heat Score Forecast');
    await expect(heatScoreLabel).toBeVisible();

    // 8. Check for Confidence Interval text to prove ML results are rendered
    const ciText = page.locator('text=95% Confidence Interval');
    await expect(ciText.first()).toBeVisible();
  });
});
