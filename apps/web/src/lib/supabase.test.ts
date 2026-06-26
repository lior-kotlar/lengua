import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { createClient } = vi.hoisted(() => ({
  createClient: vi.fn(() => ({ __marker: 'supabase-client' })),
}));

vi.mock('@supabase/supabase-js', () => ({ createClient }));

function stubCompleteEnv() {
  vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000');
  vi.stubEnv('VITE_SUPABASE_URL', 'http://localhost:54321');
  vi.stubEnv('VITE_SUPABASE_ANON_KEY', 'anon-key');
}

describe('getSupabaseClient', () => {
  beforeEach(() => {
    createClient.mockClear();
    vi.resetModules(); // reset the module-level singleton between cases
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('creates the client from env on first use and caches it', async () => {
    stubCompleteEnv();
    const { getSupabaseClient } = await import('@/lib/supabase');

    const first = getSupabaseClient();
    const second = getSupabaseClient();

    expect(first).toBe(second);
    expect(createClient).toHaveBeenCalledTimes(1);
    expect(createClient).toHaveBeenCalledWith(
      'http://localhost:54321',
      'anon-key',
      expect.objectContaining({
        auth: expect.objectContaining({ autoRefreshToken: true }),
      }),
    );
  });

  it('fails fast with a clear error when a required var is missing', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000');
    vi.stubEnv('VITE_SUPABASE_URL', '');
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', 'anon-key');
    const { getSupabaseClient } = await import('@/lib/supabase');

    expect(() => getSupabaseClient()).toThrowError(/VITE_SUPABASE_URL/);
    expect(createClient).not.toHaveBeenCalled();
  });
});
