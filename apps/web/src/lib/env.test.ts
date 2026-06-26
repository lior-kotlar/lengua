import { afterEach, describe, expect, it, vi } from 'vitest';

import { readEnv } from '@/lib/env';

const COMPLETE = {
  VITE_API_BASE_URL: 'http://localhost:8000',
  VITE_SUPABASE_URL: 'http://localhost:54321',
  VITE_SUPABASE_ANON_KEY: 'anon-key',
};

describe('readEnv', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('returns a typed env when every required var is present', () => {
    expect(readEnv(COMPLETE)).toEqual({
      apiBaseUrl: 'http://localhost:8000',
      supabaseUrl: 'http://localhost:54321',
      supabaseAnonKey: 'anon-key',
    });
  });

  it('throws a clear error naming a single missing var', () => {
    expect(() => readEnv({ ...COMPLETE, VITE_SUPABASE_URL: '' })).toThrowError(
      /VITE_SUPABASE_URL/,
    );
  });

  it('treats a whitespace-only value as missing', () => {
    expect(() =>
      readEnv({ ...COMPLETE, VITE_SUPABASE_ANON_KEY: '   ' }),
    ).toThrowError(/VITE_SUPABASE_ANON_KEY/);
  });

  it('lists every missing var in one error', () => {
    expect(() => readEnv({})).toThrowError(
      /VITE_API_BASE_URL.*VITE_SUPABASE_URL.*VITE_SUPABASE_ANON_KEY/,
    );
  });

  it('points the operator at .env.example', () => {
    expect(() => readEnv({})).toThrowError(/\.env\.example/);
  });

  it('defaults to import.meta.env when no source is passed', () => {
    vi.stubEnv('VITE_API_BASE_URL', COMPLETE.VITE_API_BASE_URL);
    vi.stubEnv('VITE_SUPABASE_URL', COMPLETE.VITE_SUPABASE_URL);
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', COMPLETE.VITE_SUPABASE_ANON_KEY);

    expect(readEnv()).toEqual({
      apiBaseUrl: COMPLETE.VITE_API_BASE_URL,
      supabaseUrl: COMPLETE.VITE_SUPABASE_URL,
      supabaseAnonKey: COMPLETE.VITE_SUPABASE_ANON_KEY,
    });
  });
});
