import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { get, put } = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, getApiClient: () => ({ GET: get, PUT: put }) };
});

import {
  proficiencyKey,
  useProficiencyQuery,
  useSetProficiencyBand,
} from '@/lib/proficiency';

function ok<T>(data: T) {
  return Promise.resolve({
    data,
    error: undefined,
    response: new Response(null, { status: 200 }),
  });
}

const LEVEL = { band: 'B1', progress: 0.4, score: 2.4 };

function makeClient() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, wrapper };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('proficiencyKey', () => {
  it('keys per language id', () => {
    expect(proficiencyKey(7)).toEqual(['proficiency', 7]);
  });
});

describe('useProficiencyQuery', () => {
  it('fetches the level for a language id', async () => {
    get.mockReturnValue(ok(LEVEL));
    const { wrapper } = makeClient();

    const { result } = renderHook(() => useProficiencyQuery(7), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(get).toHaveBeenCalledWith('/proficiency/{language_id}', {
      params: { path: { language_id: 7 } },
    });
    expect(result.current.data).toEqual(LEVEL);
  });

  it('is disabled (no request) when the language id is null', () => {
    const { wrapper } = makeClient();

    const { result } = renderHook(() => useProficiencyQuery(null), { wrapper });

    expect(result.current.fetchStatus).toBe('idle');
    expect(get).not.toHaveBeenCalled();
  });
});

describe('useSetProficiencyBand', () => {
  it('PUTs the new band and invalidates the proficiency query', async () => {
    put.mockReturnValue(ok({ band: 'C1', progress: 0, score: 4 }));
    const { queryClient, wrapper } = makeClient();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useSetProficiencyBand(7), { wrapper });
    await result.current.mutateAsync('C1');

    expect(put).toHaveBeenCalledWith('/proficiency/{language_id}', {
      params: { path: { language_id: 7 } },
      body: { band: 'C1' },
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['proficiency', 7] });
  });
});
