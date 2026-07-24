import { test, expect } from '@playwright/test';

test.describe('ClimaSentinel Forecast E2E', () => {
  test('should display the honest forecast-rule baseline for every horizon', async ({ page }) => {
    test.setTimeout(240_000);

    // 1. Navigate to the forecast page
    await page.goto('/forecast');

    // 2. Verify the hero title loaded
    await expect(page.getByRole('heading', { name: 'Climate Risk Forecast' })).toBeVisible();
    const betaBadge = page.getByLabel('Forecast feature is in beta');
    await expect(betaBadge).toBeVisible();
    await expect(betaBadge).toHaveText('Beta');
    await expect(page.getByLabel('Forecast note')).toContainText(
      'Heat has limited backtest evidence'
    );
    await expect(page.getByLabel('Forecast note')).toContainText(
      'Rain performed poorly in backtests'
    );
    await expect(page.getByLabel('Forecast note')).toContainText(
      'Wind, air quality and river lack observed validation'
    );
    await expect(page.getByLabel('Forecast note')).toContainText(
      'Missing inputs are marked unavailable'
    );
    await expect(page.getByLabel('Forecast note')).toContainText(
      'Scores are point estimates without confidence bands'
    );

    // 3. Verify there are no 500 errors
    const bodyText = await page.locator('body').textContent();
    expect(bodyText).not.toContain('500 Internal Server Error');

    // 4. Wait for the backend rollout to expose this release's explicit rule
    // contract. Railway deployments are detached, so an HTTP-ready frontend
    // can briefly coexist with the previous backend release.
    await expect.poll(async () => {
      const responsePromise = page.waitForResponse(
        (response) => response.url().includes(
          '/data/city/paris_fr/forecast?horizon_days=3'
        ),
        { timeout: 15_000 },
      );
      await page.click('text=Paris, FR');
      const response = await responsePromise;
      if (!response.ok()) return `http-${response.status()}`;
      const responseBody = await response.json();
      return `${responseBody.forecast_method}:${responseBody.prediction_source}`;
    }, {
      message: 'waiting for the staging backend rule-baseline release',
      timeout: 180_000,
      intervals: [5_000],
    }).toBe('forecast_rules_baseline:same_vintage_forecast_rules');

    // 5. Exercise each horizon and verify the rule-policy contract end to end.
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
        prediction_source: 'same_vintage_forecast_rules',
        model_version: null,
        forecast_method: 'forecast_rules_baseline',
        model_target_components: [],
        rule_based_components: expect.arrayContaining([
          'heat',
          'rain',
          'wind',
          'air',
          'river',
        ]),
      });
      expect(responseBody.feature_schema_version).toEqual(expect.any(String));
      expect(responseBody.feature_ingestion_run_id).toEqual(expect.any(String));
      expect(responseBody.feature_ingested_at_utc).toEqual(expect.any(String));
      expect(responseBody.forecast_origin_time_zone).toEqual(expect.any(String));
      expect(responseBody.forecast_primary_driver_method).toBe('forecast_rule');
      expect(responseBody.total_uncertainty_method).toBe('none');
      expect(responseBody.total_ci_lower).toBeNull();
      expect(responseBody.total_ci_upper).toBeNull();
      expect(responseBody.total_confidence_margin).toBeNull();

      const heatForecast = responseBody.sub_scores_forecast.heat_score;
      expect(heatForecast).toMatchObject({
          available: true,
          method: 'forecast_rule',
          validation_status: 'era5_backtested_limited',
          uncertainty_method: 'none',
          ci_lower: null,
          ci_upper: null,
          confidence_margin: null,
          unavailable_reason: null,
      });
      expect(heatForecast.estimated_score).toEqual(expect.any(Number));
      expect(heatForecast.provenance).toEqual(expect.any(String));
      expect(heatForecast.method_reason).toContain('Reviewed operational baseline');

      const rainForecast = responseBody.sub_scores_forecast.rain_score;
      expect(rainForecast).toMatchObject({
        available: true,
        method: 'forecast_rule',
        validation_status: 'era5_backtested_insufficient_skill',
        uncertainty_method: 'none',
        ci_lower: null,
        ci_upper: null,
        confidence_margin: null,
        unavailable_reason: null,
      });
      expect(rainForecast.estimated_score).toEqual(expect.any(Number));
      expect(rainForecast.provenance).toEqual(expect.any(String));
      expect(rainForecast.method_reason).toContain('insufficient predictive skill');

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
        expect(ruleForecast.provenance).toEqual(expect.any(String));
        expect(ruleForecast.method_reason).toEqual(expect.any(String));
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

      for (const label of ['Heat', 'Rain', 'Wind', 'Air quality', 'River / flood']) {
        const ruleCard = page.getByRole('article', { name: `${label} forecast` });
        await expect(ruleCard).toBeVisible();
        await expect(ruleCard.getByText('Model spread band', { exact: true })).toHaveCount(0);
      }

      await expect(page.getByText('95% Confidence Interval')).toHaveCount(0);
    }
  });
});
