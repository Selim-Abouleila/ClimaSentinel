import { test, expect } from '@playwright/test';

test.describe('ClimaSentinel Forecast E2E', () => {
  test('should navigate to forecast page, select Paris, and display ML scoring cards', async ({ page }) => {
    const expectedModelVersion = process.env.EXPECTED_MODEL_VERSION;
    // 1. Navigate to the forecast page
    await page.goto('/forecast');

    // 2. Verify the hero title loaded
    await expect(page.getByRole('heading', { name: 'AI Tipping Forecast' })).toBeVisible();
    await expect(page.getByLabel('Forecast validation scope')).toContainText(
      'Model validation currently covers heat and rainfall only'
    );

    // 3. Verify there are no 500 errors
    const bodyText = await page.locator('body').textContent();
    expect(bodyText).not.toContain('500 Internal Server Error');

    // 4. Select the City
    await page.click('text=Paris, FR');

    // 5. Exercise every genuine horizon-specific model through the deployed API.
    for (const horizon of [
      { button: '+1 Day Tomorrow', day: 1 },
      { button: '+2 Days 48 hours', day: 2 },
      { button: '+3 Days 72 hours', day: 3 },
    ]) {
      const [apiResponse] = await Promise.all([
        page.waitForResponse((response) =>
          response.url().includes(`/data/city/paris_fr/forecast?horizon_days=${horizon.day}`)
        ),
        page.getByRole('button', { name: horizon.button, exact: true }).click(),
      ]);
      expect(apiResponse.ok()).toBeTruthy();
      const responseBody = await apiResponse.json();
      expect(responseBody).toMatchObject({
        horizon_days: horizon.day,
        prediction_source: 'mlflow_registry',
      });
      if (expectedModelVersion) {
        expect(responseBody.model_version).toBe(expectedModelVersion);
      } else {
        expect(responseBody.model_version).toMatch(/^\d+$/);
      }

      await expect(
        page.getByRole('heading', { name: `Paris, FR · Day +${horizon.day}` })
      ).toBeVisible({ timeout: 15000 });
      await expect(page.getByText(`Est. Total Risk (Day +${horizon.day})`)).toBeVisible();
      await expect(page.getByText('Heat Score Forecast')).toBeVisible();
      await expect(page.getByText('95% Confidence Interval').first()).toBeVisible();
    }
  });
});
