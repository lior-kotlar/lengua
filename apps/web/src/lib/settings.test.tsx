import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock only `getApiClient`; keep the real `unwrap`/`ApiError` so the typed result path is exercised.
const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, getApiClient: () => ({ GET: get }) };
});

import {
  DISCOVER_COUNT_KEY,
  settingsKey,
  useSettingsQuery,
} from '@/lib/settings';

function ok<T>(data: T, status = 200) {
  return Promise.resolve({
    data,
    error: undefined,
    response: new Response(null, { status }),
  });
}

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('settings constants', () => {
  it('exposes the known discover-count key and a stable query key', () => {
    expect(DISCOVER_COUNT_KEY).toBe('discover_count');
    expect(settingsKey()).toEqual(['settings']);
  });
});

describe('useSettingsQuery', () => {
  it('GETs /settings and returns the values map', async () => {
    get.mockReturnValue(ok({ values: { discover_count: '7' } }));
    const { result } = renderHook(() => useSettingsQuery(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(get).toHaveBeenCalledWith('/settings');
    expect(result.current.data).toEqual({ values: { discover_count: '7' } });
  });
});
