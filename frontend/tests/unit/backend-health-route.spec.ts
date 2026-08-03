import { expect, test } from '@playwright/test';

import { GET } from '../../src/app/api/backend-health/route';

const originalFetch = globalThis.fetch;
const originalApiUrl = process.env.NEXT_PUBLIC_API_URL;

test.afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalApiUrl === undefined) {
    delete process.env.NEXT_PUBLIC_API_URL;
  } else {
    process.env.NEXT_PUBLIC_API_URL = originalApiUrl;
  }
});

test('proxies backend health without caching the request or response', async () => {
  process.env.NEXT_PUBLIC_API_URL = 'https://backend.example.test/';
  let requestedUrl = '';
  let requestedInit: RequestInit | undefined;

  globalThis.fetch = async (input, init) => {
    requestedUrl = String(input);
    requestedInit = init;
    return Response.json({ status: 'healthy', release_id: 'sha-run' });
  };

  const response = await GET();

  expect(requestedUrl).toBe('https://backend.example.test/health');
  expect(requestedInit?.cache).toBe('no-store');
  expect(requestedInit?.signal).toBeInstanceOf(AbortSignal);
  expect(response.status).toBe(200);
  expect(response.headers.get('cache-control')).toContain('no-store');
  await expect(response.json()).resolves.toEqual({
    status: 'healthy',
    release_id: 'sha-run',
  });
});

test('returns an uncached 502 when the backend cannot be reached', async () => {
  globalThis.fetch = async () => {
    throw new Error('backend unavailable');
  };

  const response = await GET();

  expect(response.status).toBe(502);
  expect(response.headers.get('cache-control')).toContain('no-store');
  await expect(response.json()).resolves.toEqual({
    status: 'unavailable',
    detail: 'Backend health check failed',
  });
});
