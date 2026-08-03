const NO_STORE_HEADERS = {
  'Cache-Control': 'no-store, no-cache, max-age=0, must-revalidate',
  Pragma: 'no-cache',
  Expires: '0',
};

export const dynamic = 'force-dynamic';

function backendHealthUrl(): string {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
  return `${apiBaseUrl.replace(/\/+$/, '')}/health`;
}

export async function GET(): Promise<Response> {
  try {
    const upstreamResponse = await fetch(backendHealthUrl(), {
      cache: 'no-store',
      signal: AbortSignal.timeout(8_000),
      headers: {
        Accept: 'application/json',
        'Cache-Control': 'no-cache',
        Pragma: 'no-cache',
      },
    });
    const body = await upstreamResponse.text();

    return new Response(body, {
      status: upstreamResponse.status,
      headers: {
        ...NO_STORE_HEADERS,
        'Content-Type': upstreamResponse.headers.get('content-type') || 'application/json',
      },
    });
  } catch {
    return Response.json(
      {
        status: 'unavailable',
        detail: 'Backend health check failed',
      },
      {
        status: 502,
        headers: NO_STORE_HEADERS,
      },
    );
  }
}
