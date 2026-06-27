import { beforeEach, describe, expect, it, vi } from 'vitest';

// Hoisted mock fns (vi.mock factories are hoisted above imports — see supabase.test.ts pattern).
const { getSession, refreshSession, signOut, readEnvMock } = vi.hoisted(() => ({
  getSession: vi.fn(),
  refreshSession: vi.fn(),
  signOut: vi.fn(),
  readEnvMock: vi.fn(),
}));

vi.mock('@/lib/supabase', () => ({
  getSupabaseClient: () => ({ auth: { getSession, refreshSession, signOut } }),
}));
vi.mock('@/lib/env', () => ({ readEnv: readEnvMock }));

import {
  ApiError,
  createAuthedApiClient,
  createRefreshRetryFetch,
  getApiClient,
  isApiError,
  resetApiClient,
  toApiError,
  unwrap,
} from '@/lib/api-client';

/** A JSON Response with optional extra headers. */
function jsonResponse(
  body: unknown,
  status: number,
  headers: Record<string, string> = {},
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

/** A custom fetch that records outgoing requests and returns a fresh response per call. */
function capturingFetch(makeResponse: (request: Request) => Response) {
  const requests: Request[] = [];
  const fetch = vi.fn(async (request: Request) => {
    requests.push(request);
    return makeResponse(request);
  });
  return { fetch, requests };
}

/** Resolve a promise to its rejection value (or null if it unexpectedly resolves). */
async function rejection(promise: Promise<unknown>): Promise<unknown> {
  return promise.then(
    () => null,
    (error: unknown) => error,
  );
}

beforeEach(() => {
  resetApiClient();
  getSession.mockReset();
  getSession.mockResolvedValue({
    data: { session: { access_token: 'jwt-123' } },
    error: null,
  });
  refreshSession.mockReset();
  refreshSession.mockResolvedValue({
    data: { session: { access_token: 'jwt-refreshed' } },
    error: null,
  });
  signOut.mockReset();
  signOut.mockResolvedValue({ error: null });
  readEnvMock.mockReset();
  readEnvMock.mockReturnValue({
    apiBaseUrl: 'http://api.test',
    supabaseUrl: 'http://supabase.test',
    supabaseAnonKey: 'anon',
  });
});

describe('auth middleware', () => {
  it('attaches the bearer token from the current Supabase session', async () => {
    const { fetch, requests } = capturingFetch(() =>
      jsonResponse({ status: 'ok' }, 200),
    );
    const client = createAuthedApiClient({ baseUrl: 'http://api.test', fetch });

    await client.GET('/me');

    expect(requests).toHaveLength(1);
    expect(requests[0].headers.get('Authorization')).toBe('Bearer jwt-123');
    expect(requests[0].url).toBe('http://api.test/me');
    expect(getSession).toHaveBeenCalledTimes(1);
  });

  it('omits the Authorization header when there is no session', async () => {
    getSession.mockResolvedValue({ data: { session: null }, error: null });
    const { fetch, requests } = capturingFetch(() => jsonResponse({}, 200));
    const client = createAuthedApiClient({ baseUrl: 'http://api.test', fetch });

    await client.GET('/me');

    expect(requests[0].headers.get('Authorization')).toBeNull();
  });

  it('uses an injected token source instead of the session when provided', async () => {
    const { fetch, requests } = capturingFetch(() => jsonResponse({}, 200));
    const client = createAuthedApiClient({
      baseUrl: 'http://api.test',
      fetch,
      getAccessToken: async () => 'injected-token',
    });

    await client.GET('/me');

    expect(requests[0].headers.get('Authorization')).toBe(
      'Bearer injected-token',
    );
    expect(getSession).not.toHaveBeenCalled();
  });
});

describe('unwrap', () => {
  it('returns the typed data on a 2xx response', async () => {
    const payload = {
      id: 'u1',
      email: 'demo@example.com',
      email_verified: true,
      plan: 'free',
      languages: [],
    };
    const { fetch } = capturingFetch(() => jsonResponse(payload, 200));
    const client = createAuthedApiClient({ baseUrl: 'http://api.test', fetch });

    const me = await unwrap(client.GET('/me'));

    expect(me).toEqual(payload);
  });

  it('throws a typed ApiError for a 429 rate_limited (with Retry-After)', async () => {
    const { fetch } = capturingFetch(() =>
      jsonResponse({ code: 'rate_limited' }, 429, { 'Retry-After': '30' }),
    );
    const client = createAuthedApiClient({ baseUrl: 'http://api.test', fetch });

    const error = await rejection(unwrap(client.GET('/me')));

    expect(error).toBeInstanceOf(ApiError);
    expect(isApiError(error)).toBe(true);
    if (!isApiError(error)) throw new Error('expected ApiError');
    expect(error.status).toBe(429);
    expect(error.code).toBe('rate_limited');
    expect(error.retryAfter).toBe(30);
    // No `message` field on this body → derived default mentions the status.
    expect(error.message).toContain('429');
  });

  it('surfaces email_unverified (403) as a typed error', async () => {
    const { fetch } = capturingFetch(() =>
      jsonResponse({ code: 'email_unverified' }, 403),
    );
    const client = createAuthedApiClient({ baseUrl: 'http://api.test', fetch });

    const error = await rejection(unwrap(client.GET('/me')));

    expect(isApiError(error)).toBe(true);
    if (!isApiError(error)) throw new Error('expected ApiError');
    expect(error.status).toBe(403);
    expect(error.code).toBe('email_unverified');
    expect(error.retryAfter).toBeUndefined();
  });

  it('keeps extra body fields (daily_cap_reached kind) on the error', async () => {
    const { fetch } = capturingFetch(() =>
      jsonResponse({ code: 'daily_cap_reached', kind: 'generate' }, 429),
    );
    const client = createAuthedApiClient({ baseUrl: 'http://api.test', fetch });

    const error = await rejection(unwrap(client.GET('/me')));

    if (!isApiError(error)) throw new Error('expected ApiError');
    expect(error.code).toBe('daily_cap_reached');
    expect(error.body).toMatchObject({ kind: 'generate' });
  });

  it('uses the body message for daily_limit_reached', async () => {
    const message = 'Daily limit reached, please try again tomorrow.';
    const { fetch } = capturingFetch(() =>
      jsonResponse({ code: 'daily_limit_reached', message }, 429),
    );
    const client = createAuthedApiClient({ baseUrl: 'http://api.test', fetch });

    const error = await rejection(unwrap(client.GET('/me')));

    if (!isApiError(error)) throw new Error('expected ApiError');
    expect(error.code).toBe('daily_limit_reached');
    expect(error.message).toBe(message);
  });

  it('wraps a transport failure as ApiError with status 0', async () => {
    const boom = new Error('connection refused');
    const fetch = vi.fn(async () => {
      throw boom;
    });
    const client = createAuthedApiClient({ baseUrl: 'http://api.test', fetch });

    const error = await rejection(unwrap(client.GET('/me')));

    if (!isApiError(error)) throw new Error('expected ApiError');
    expect(error.status).toBe(0);
    expect(error.code).toBe('network_error');
    expect(error.message).toBe('connection refused');
    expect(error.cause).toBe(boom);
  });

  it('handles a non-Error transport throw with a default message', async () => {
    const fetch = vi.fn(async () => {
      throw 'weird-non-error';
    });
    const client = createAuthedApiClient({ baseUrl: 'http://api.test', fetch });

    const error = await rejection(unwrap(client.GET('/me')));

    if (!isApiError(error)) throw new Error('expected ApiError');
    expect(error.message).toBe('Network request failed');
    expect(error.cause).toBe('weird-non-error');
  });
});

describe('toApiError', () => {
  it('falls back to FastAPI detail then a generic message', () => {
    const withDetail = toApiError(new Response(null, { status: 404 }), {
      detail: 'Not found',
    });
    expect(withDetail.message).toBe('Not found');
    expect(withDetail.code).toBeUndefined();
    expect(withDetail.retryAfter).toBeUndefined();

    const nonObject = toApiError(new Response(null, { status: 500 }), 'oops');
    expect(nonObject.message).toBe('Request failed with status 500');
    expect(nonObject.body).toBe('oops');

    const nullBody = toApiError(new Response(null, { status: 500 }), null);
    expect(nullBody.message).toBe('Request failed with status 500');
  });

  it('parses Retry-After defensively', () => {
    const invalid = toApiError(
      new Response(null, { status: 503, headers: { 'Retry-After': 'soon' } }),
      { code: 'server_busy', message: 'busy' },
    );
    expect(invalid.retryAfter).toBeUndefined();
    expect(invalid.code).toBe('server_busy');
    expect(invalid.message).toBe('busy');

    const zero = toApiError(
      new Response(null, { status: 429, headers: { 'Retry-After': '0' } }),
      { code: 'rate_limited' },
    );
    expect(zero.retryAfter).toBe(0);

    const blank = toApiError(
      new Response(null, { status: 429, headers: { 'Retry-After': '' } }),
      { code: 'rate_limited' },
    );
    expect(blank.retryAfter).toBeUndefined();
  });
});

describe('isApiError', () => {
  it('narrows ApiError and rejects other values', () => {
    expect(isApiError(new ApiError({ status: 500, message: 'x' }))).toBe(true);
    expect(isApiError(new Error('plain'))).toBe(false);
    expect(isApiError({ status: 500 })).toBe(false);
    expect(isApiError(null)).toBe(false);
  });
});

describe('getApiClient', () => {
  it('builds from env, caches the instance, and resets', () => {
    const first = getApiClient();
    const second = getApiClient();
    expect(first).toBe(second);
    expect(readEnvMock).toHaveBeenCalledTimes(1);

    resetApiClient();
    const third = getApiClient();
    expect(third).not.toBe(first);
    expect(readEnvMock).toHaveBeenCalledTimes(2);
  });
});

describe('createRefreshRetryFetch (4.3.7)', () => {
  it('refreshes once and retries with the new token on a 401', async () => {
    const seen: Request[] = [];
    const responses = [
      new Response(null, { status: 401 }),
      jsonResponse({ ok: true }, 200),
    ];
    const baseFetch = vi.fn(async (request: Request) => {
      seen.push(request);
      return responses[seen.length - 1];
    });
    const refresh = vi.fn(async () => 'new-token');
    const onAuthFailure = vi.fn();
    const wrapped = createRefreshRetryFetch(baseFetch, refresh, onAuthFailure);

    const response = await wrapped(
      new Request('http://api.test/me', {
        headers: { Authorization: 'Bearer old' },
      }),
    );

    expect(response.status).toBe(200);
    expect(baseFetch).toHaveBeenCalledTimes(2);
    expect(seen[0].headers.get('Authorization')).toBe('Bearer old');
    expect(seen[1].headers.get('Authorization')).toBe('Bearer new-token');
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(onAuthFailure).not.toHaveBeenCalled();
  });

  it('signs out and surfaces the original 401 when refresh fails', async () => {
    const baseFetch = vi.fn(async () => new Response(null, { status: 401 }));
    const refresh = vi.fn(async () => null);
    const onAuthFailure = vi.fn();
    const wrapped = createRefreshRetryFetch(baseFetch, refresh, onAuthFailure);

    const response = await wrapped(new Request('http://api.test/me'));

    expect(response.status).toBe(401);
    expect(baseFetch).toHaveBeenCalledTimes(1);
    expect(onAuthFailure).toHaveBeenCalledTimes(1);
  });

  it('passes through a non-401 without refreshing', async () => {
    const baseFetch = vi.fn(async () => new Response(null, { status: 200 }));
    const refresh = vi.fn();
    const wrapped = createRefreshRetryFetch(baseFetch, refresh, vi.fn());

    const response = await wrapped(new Request('http://api.test/me'));

    expect(response.status).toBe(200);
    expect(refresh).not.toHaveBeenCalled();
    expect(baseFetch).toHaveBeenCalledTimes(1);
  });

  it('retries at most once (no loop) when the retry also 401s', async () => {
    const baseFetch = vi.fn(async () => new Response(null, { status: 401 }));
    const refresh = vi.fn(async () => 'new-token');
    const onAuthFailure = vi.fn();
    const wrapped = createRefreshRetryFetch(baseFetch, refresh, onAuthFailure);

    const response = await wrapped(new Request('http://api.test/me'));

    expect(response.status).toBe(401);
    expect(baseFetch).toHaveBeenCalledTimes(2);
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(onAuthFailure).not.toHaveBeenCalled();
  });
});

describe('401 refresh + retry through the client', () => {
  it('retries with the refreshed token (default supabase refresh)', async () => {
    const seen: Request[] = [];
    let calls = 0;
    const fetch = vi.fn(async (request: Request) => {
      seen.push(request);
      calls += 1;
      return calls === 1
        ? jsonResponse({ code: 'x' }, 401)
        : jsonResponse({ status: 'ok' }, 200);
    });
    const client = createAuthedApiClient({ baseUrl: 'http://api.test', fetch });

    const me = await unwrap(client.GET('/me'));

    expect(me).toEqual({ status: 'ok' });
    expect(seen[0].headers.get('Authorization')).toBe('Bearer jwt-123');
    expect(seen[1].headers.get('Authorization')).toBe('Bearer jwt-refreshed');
    expect(refreshSession).toHaveBeenCalledTimes(1);
    expect(signOut).not.toHaveBeenCalled();
  });

  it('signs out (default handler) when the refresh itself fails', async () => {
    refreshSession.mockResolvedValue({
      data: { session: null },
      error: { message: 'refresh failed' },
    });
    const fetch = vi.fn(async () => jsonResponse({ code: 'x' }, 401));
    const client = createAuthedApiClient({ baseUrl: 'http://api.test', fetch });

    const error = await rejection(unwrap(client.GET('/me')));

    if (!isApiError(error)) throw new Error('expected ApiError');
    expect(error.status).toBe(401);
    expect(signOut).toHaveBeenCalledTimes(1);
  });

  it('signs out when the refresh call throws', async () => {
    refreshSession.mockRejectedValue(new Error('network down'));
    const fetch = vi.fn(async () => jsonResponse({ code: 'x' }, 401));
    const client = createAuthedApiClient({ baseUrl: 'http://api.test', fetch });

    const error = await rejection(unwrap(client.GET('/me')));

    if (!isApiError(error)) throw new Error('expected ApiError');
    expect(error.status).toBe(401);
    expect(signOut).toHaveBeenCalledTimes(1);
  });

  it('uses the global fetch when none is injected', async () => {
    const globalFetch = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse({ status: 'ok' }, 200));
    try {
      const client = createAuthedApiClient({ baseUrl: 'http://api.test' });
      const me = await unwrap(client.GET('/me'));
      expect(me).toEqual({ status: 'ok' });
      expect(globalFetch).toHaveBeenCalledTimes(1);
    } finally {
      globalFetch.mockRestore();
    }
  });

  it('coalesces concurrent 401s into a single refresh (single-flight)', async () => {
    const fetch = vi.fn(async (request: Request) =>
      request.headers.get('Authorization') === 'Bearer jwt-refreshed'
        ? jsonResponse({ ok: true }, 200)
        : jsonResponse({ code: 'x' }, 401),
    );
    const client = createAuthedApiClient({ baseUrl: 'http://api.test', fetch });

    const [a, b] = await Promise.all([
      unwrap(client.GET('/me')),
      unwrap(client.GET('/me')),
    ]);

    expect(a).toEqual({ ok: true });
    expect(b).toEqual({ ok: true });
    expect(refreshSession).toHaveBeenCalledTimes(1);
  });
});
