import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, getApiClient: () => ({ GET: get }) };
});

import {
  featureFlagsKey,
  useFeatureFlag,
  useFeatureFlagsQuery,
  WORD_OF_THE_DAY_FLAG,
} from '@/lib/feature-flags';

function ok<T>(data: T) {
  return Promise.resolve({
    data,
    error: undefined,
    response: new Response(null, { status: 200 }),
  });
}

function fail(status: number) {
  return Promise.resolve({
    data: undefined,
    error: { detail: 'nope' },
    response: new Response(null, { status }),
  });
}

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { wrapper };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('featureFlagsKey', () => {
  it('is a stable query key', () => {
    expect(featureFlagsKey()).toEqual(['feature-flags']);
  });
});

describe('useFeatureFlagsQuery', () => {
  it('fetches the resolved flag map from GET /feature-flags', async () => {
    get.mockReturnValue(ok({ word_of_the_day: true }));
    const { wrapper } = makeWrapper();

    const { result } = renderHook(() => useFeatureFlagsQuery(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(get).toHaveBeenCalledWith('/feature-flags');
    expect(result.current.data).toEqual({ word_of_the_day: true });
  });
});

describe('useFeatureFlag', () => {
  it('returns the resolved boolean for a known flag', async () => {
    get.mockReturnValue(ok({ [WORD_OF_THE_DAY_FLAG]: true }));
    const { wrapper } = makeWrapper();

    const { result } = renderHook(() => useFeatureFlag(WORD_OF_THE_DAY_FLAG), {
      wrapper,
    });

    await waitFor(() => expect(result.current).toBe(true));
  });

  it('defaults to false while the map is loading', () => {
    get.mockReturnValue(new Promise(() => {})); // never resolves
    const { wrapper } = makeWrapper();

    const { result } = renderHook(() => useFeatureFlag(WORD_OF_THE_DAY_FLAG), {
      wrapper,
    });

    expect(result.current).toBe(false);
  });

  it('defaults to false for a flag absent from the map', async () => {
    get.mockReturnValue(ok({ word_of_the_day: true }));
    const { wrapper } = makeWrapper();

    const { result } = renderHook(() => useFeatureFlag('not_a_real_flag'), {
      wrapper,
    });

    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(result.current).toBe(false);
  });

  it('fails safe to false when the request errors', async () => {
    get.mockReturnValue(fail(500));
    const { wrapper } = makeWrapper();

    const { result } = renderHook(() => useFeatureFlag(WORD_OF_THE_DAY_FLAG), {
      wrapper,
    });

    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(result.current).toBe(false);
  });
});
