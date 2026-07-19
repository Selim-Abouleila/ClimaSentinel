import { test, expect } from '@playwright/test';

test.describe('ClimaSentinel Forecast E2E', () => {
  test('should display honest learned and forecast-rule outputs for every horizon', async ({ page }) => {
    const expectedModelVersion = process.env.EXPECTED_MODEL_VERSION;
    // 1. Navigate to the forecast page
    await page.goto('/forecast');

    // 2. Verify the hero title loaded
    await expect(page.getByRole('heading', { name: 'AI Tipping Forecast' })).toBeVisible();
    await expect(page.getByLabel('Forecast validation scope')).toContainText(
      'Heat and rainfall are learned from realized ERA5 outcomes'
    );
    await expect(page.getByLabel('Forecast validation scope')).toContainText(
      'Missing source forecasts are shown as unavailable, never as zero risk'
    );

    // 3. Verify there are no 500 errors
    const bodyText = await page.locator('body').textContent();
    expect(bodyText).not.toContain('500 Internal Server Error');

    // 4. Select the City
    await page.click('text=Paris, FR');

    // 5. Exercise each horizon and verify the hybrid method contract end to end.
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
        forecast_method: 'hybrid_ml_and_forecast_rules',
        model_target_components: expect.arrayContaining(['heat', 'rain']),
        rule_based_components: expect.arrayContaining([
          'wind',
          'air',
          'river',
        ]),
      });
      expect(responseBody.feature_schema_version).toEqual(expect.any(String));
      expect(responseBody.feature_ingestion_run_id).toEqual(expect.any(String));
      expect(responseBody.feature_ingested_at_utc).toEqual(expect.any(String));
      expect(responseBody.forecast_origin_time_zone).toEqual(expect.any(String));
      expect(['learned_model', 'forecast_rule']).toContain(
        responseBody.forecast_primary_driver_method
      );

      if (responseBody.total_uncertainty_method === 'tree_spread_not_calibrated') {
        expect(responseBody.forecast_primary_driver_method).toBe('learned_model');
        expect(responseBody.total_ci_lower).toEqual(expect.any(Number));
        expect(responseBody.total_ci_upper).toEqual(expect.any(Number));
        expect(responseBody.total_confidence_margin).toEqual(expect.any(Number));
      } else {
        expect(responseBody.total_uncertainty_method).toBe('none');
        expect(responseBody.total_ci_lower).toBeNull();
        expect(responseBody.total_ci_upper).toBeNull();
        expect(responseBody.total_confidence_margin).toBeNull();
      }

      if (expectedModelVersion) {
        expect(responseBody.model_version).toBe(expectedModelVersion);
      } else {
        expect(responseBody.model_version).toMatch(/^\d+$/);
      }

      for (const component of ['heat_score', 'rain_score']) {
        const learnedForecast = responseBody.sub_scores_forecast[component];
        expect(learnedForecast).toMatchObject({
          available: true,
          method: 'learned_model',
          validation_status: 'era5_realized_validated',
          uncertainty_method: 'tree_spread_not_calibrated',
          unavailable_reason: null,
        });
        expect(learnedForecast.estimated_score).toEqual(expect.any(Number));
        expect(learnedForecast.ci_lower).toEqual(expect.any(Number));
        expect(learnedForecast.ci_upper).toEqual(expect.any(Number));
        expect(learnedForecast.confidence_margin).toEqual(expect.any(Number));
      }

      for (const component of ['wind_score', 'air_score', 'river_score']) {
        const ruleForecast = responseBody.sub_scores_forecast[component];
        expect(ruleForecast).toMatchObject({
          method: 'forecast_rule',
          validation_status: 'not_observation_validated',
          uncertainty_method: 'none',
          ci_lower: null,
          ci_upper: null,
          confidence_margin: null,
        });
        expect(ruleForecast.available).toEqual(expect.any(Boolean));
        if (ruleForecast.available) {
          expect(ruleForecast.estimated_score).toEqual(expect.any(Number));
          expect(ruleForecast.unavailable_reason).toBeNull();
        } else {
          expect(ruleForecast.estimated_score).toBeNull();
          expect(ruleForecast.unavailable_reason).toEqual(expect.any(String));
        }
      }

      await expect(
        page.getByRole('heading', { name: `Paris, FR · Day +${horizon.day}` })
      ).toBeVisible({ timeout: 15000 });
      await expect(page.getByText(`Est. Total Risk (Day +${horizon.day})`)).toBeVisible();

      for (const label of ['Heat', 'Rain']) {
        const learnedCard = page.getByRole('article', { name: `${label} forecast` });
        await expect(learnedCard.getByText('Learned model', { exact: true })).toBeVisible();
        await expect(learnedCard.getByText('Model spread band', { exact: true })).toBeVisible();
        await expect(learnedCard).toContainText('not a calibrated interval');
      }

      for (const label of ['Wind', 'Air quality', 'River / flood']) {
        const ruleCard = page.getByRole('article', { name: `${label} forecast` });
        await expect(ruleCard.getByText('Forecast rule', { exact: true })).toBeVisible();
        await expect(ruleCard.getByText('Model spread band', { exact: true })).toHaveCount(0);
      }

      await expect(page.getByText('95% Confidence Interval')).toHaveCount(0);
      await expect(page.getByLabel('Forecast provenance')).toContainText(
        'Learned: Heat, Rain'
      );
      await expect(page.getByLabel('Forecast provenance')).toContainText(
        'Forecast rules: Wind, Air quality, River / flood'
      );
    }
  });
});
