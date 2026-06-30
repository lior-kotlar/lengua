import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock only `getApiClient`; keep the real `unwrap`/`ApiError` so the typed result path is exercised.
const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, getApiClient: () => ({ POST: post }) };
});

import {
  clampDiscoverCount,
  DISCOVER_COUNT_DEFAULT,
  DISCOVER_COUNT_MAX,
  DISCOVER_COUNT_MIN,
  resolveDiscoverCount,
  useDiscover,
} from '@/lib/discover';
import type { SettingsOut } from '@/lib/settings';

function ok<T>(data: T, status = 200) {
  return Promise.resolve({
    data,
    error: undefined,
    response: new Response(null, { status }),
  });
}

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('discover count constants', () => {
  it('are sourced from the generated schema (DiscoverRequest.count bounds + default)', () => {
    expect(DISCOVER_COUNT_MIN).toBe(1);
    expect(DISCOVER_COUNT_MAX).toBe(20);
    expect(DISCOVER_COUNT_DEFAULT).toBe(5);
  });
});

describe('clampDiscoverCount', () => {
  it('keeps an in-range value', () => {
    expect(clampDiscoverCount(8)).toBe(8);
  });

  it('clamps below the minimum and above the maximum', () => {
    expect(clampDiscoverCount(0)).toBe(DISCOVER_COUNT_MIN);
    expect(clampDiscoverCount(999)).toBe(DISCOVER_COUNT_MAX);
  });

  it('rounds a fractional value', () => {
    expect(clampDiscoverCount(5.6)).toBe(6);
  });

  it('falls back to the default for a non-finite value', () => {
    expect(clampDiscoverCount(Number.NaN)).toBe(DISCOVER_COUNT_DEFAULT);
  });
});

describe('resolveDiscoverCount', () => {
  function settings(value: string | null | undefined): SettingsOut | undefined {
    if (value === undefined) {
      return undefined;
    }
    return { values: { discover_count: value } };
  }

  it('uses the saved discover_count setting', () => {
    expect(resolveDiscoverCount(settings('7'))).toBe(7);
  });

  it('clamps an out-of-range saved value into the request bounds', () => {
    expect(resolveDiscoverCount(settings('50'))).toBe(DISCOVER_COUNT_MAX);
  });

  it('falls back to the default when there are no settings', () => {
    expect(resolveDiscoverCount(undefined)).toBe(DISCOVER_COUNT_DEFAULT);
  });

  it('falls back to the default when the key is absent', () => {
    expect(resolveDiscoverCount({ values: {} })).toBe(DISCOVER_COUNT_DEFAULT);
  });

  it('falls back to the default for a blank or null value', () => {
    expect(resolveDiscoverCount(settings('   '))).toBe(DISCOVER_COUNT_DEFAULT);
    expect(resolveDiscoverCount(settings(null))).toBe(DISCOVER_COUNT_DEFAULT);
  });

  it('falls back to the default for a non-numeric value', () => {
    expect(resolveDiscoverCount(settings('lots'))).toBe(DISCOVER_COUNT_DEFAULT);
  });
});

describe('useDiscover', () => {
  it('POSTs /discover with the language id, count + topic and returns the words', async () => {
    post.mockReturnValue(ok({ words: ['house', 'water'] }));
    const { result } = renderHook(() => useDiscover(), {
      wrapper: makeWrapper(),
    });

    const out = await result.current.mutateAsync({
      languageId: 3,
      count: 5,
      topic: 'food',
    });

    // A normal discover always sends fresh:false (the contract types the field required).
    expect(post).toHaveBeenCalledWith('/discover', {
      body: { language_id: 3, count: 5, topic: 'food', fresh: false },
    });
    expect(out).toEqual(['house', 'water']);
  });

  it('passes a null topic through unchanged', async () => {
    post.mockReturnValue(ok({ words: [] }));
    const { result } = renderHook(() => useDiscover(), {
      wrapper: makeWrapper(),
    });

    await result.current.mutateAsync({ languageId: 1, count: 3, topic: null });
    expect(post).toHaveBeenCalledWith('/discover', {
      body: { language_id: 1, count: 3, topic: null, fresh: false },
    });
  });

  it('sends fresh:true on an explicit reroll (bypasses the backend reuse cache — S8)', async () => {
    post.mockReturnValue(ok({ words: ['music', 'river'] }));
    const { result } = renderHook(() => useDiscover(), {
      wrapper: makeWrapper(),
    });

    await result.current.mutateAsync({
      languageId: 3,
      count: 5,
      topic: 'food',
      fresh: true,
    });
    expect(post).toHaveBeenCalledWith('/discover', {
      body: { language_id: 3, count: 5, topic: 'food', fresh: true },
    });
  });

  it('surfaces a typed ApiError for a quota 429', async () => {
    post.mockReturnValue(
      Promise.resolve({
        data: undefined,
        error: { code: 'daily_limit_reached', message: 'Daily limit reached.' },
        response: new Response(null, { status: 429 }),
      }),
    );
    const { result } = renderHook(() => useDiscover(), {
      wrapper: makeWrapper(),
    });

    await expect(
      result.current.mutateAsync({ languageId: 1, count: 5, topic: null }),
    ).rejects.toMatchObject({ status: 429, code: 'daily_limit_reached' });
  });
});
