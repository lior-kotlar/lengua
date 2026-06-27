import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock only `getApiClient`; keep the real `unwrap`/`ApiError` so the typed-error path is exercised.
const { get, post, put, del } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  del: vi.fn(),
}));
vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return {
    ...actual,
    getApiClient: () => ({ GET: get, POST: post, PUT: put, DELETE: del }),
  };
});

import {
  useAddLanguage,
  useLanguagesQuery,
  useRemoveLanguage,
  type LanguageOut,
} from '@/lib/languages';

/** An openapi-fetch-shaped success result the real `unwrap` accepts. */
function ok<T>(data: T, status = 200) {
  return Promise.resolve({
    data,
    error: undefined,
    response: new Response(null, { status }),
  });
}

const SPANISH: LanguageOut = {
  id: 1,
  name: 'Spanish',
  code: 'es',
  vowelized: false,
};

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

describe('useLanguagesQuery', () => {
  it('fetches the user language list from GET /languages', async () => {
    get.mockReturnValue(ok([SPANISH]));
    const { wrapper } = makeClient();

    const { result } = renderHook(() => useLanguagesQuery(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(get).toHaveBeenCalledWith('/languages');
    expect(result.current.data).toEqual([SPANISH]);
  });
});

describe('useAddLanguage', () => {
  it('creates with trimmed name/code and invalidates the languages query', async () => {
    post.mockReturnValue(ok(SPANISH));
    const { queryClient, wrapper } = makeClient();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useAddLanguage(), { wrapper });
    const created = await result.current.mutateAsync({
      name: '  Spanish  ',
      code: '  es  ',
      vowelized: true,
    });

    expect(created).toEqual(SPANISH);
    expect(post).toHaveBeenCalledWith('/languages', {
      body: { name: 'Spanish', code: 'es', vowelized: true },
    });
    // Default band (no band given) → no proficiency PUT.
    expect(put).not.toHaveBeenCalled();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['languages'] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['proficiency', 1] });
  });

  it('omits the code when blank and defaults vowelized to false', async () => {
    post.mockReturnValue(ok(SPANISH));
    const { wrapper } = makeClient();

    const { result } = renderHook(() => useAddLanguage(), { wrapper });
    await result.current.mutateAsync({ name: 'Spanish' });

    expect(post).toHaveBeenCalledWith('/languages', {
      body: { name: 'Spanish', code: null, vowelized: false },
    });
  });

  it('PUTs the starting band when it is not the default A1', async () => {
    post.mockReturnValue(ok({ ...SPANISH, id: 9 }));
    put.mockReturnValue(ok({ band: 'B1', progress: 0, score: 2 }));
    const { wrapper } = makeClient();

    const { result } = renderHook(() => useAddLanguage(), { wrapper });
    await result.current.mutateAsync({ name: 'French', band: 'B1' });

    expect(put).toHaveBeenCalledWith('/proficiency/{language_id}', {
      params: { path: { language_id: 9 } },
      body: { band: 'B1' },
    });
  });

  it('does not PUT proficiency for the default A1 starting band', async () => {
    post.mockReturnValue(ok(SPANISH));
    const { wrapper } = makeClient();

    const { result } = renderHook(() => useAddLanguage(), { wrapper });
    await result.current.mutateAsync({ name: 'Spanish', band: 'A1' });

    expect(put).not.toHaveBeenCalled();
  });
});

describe('useRemoveLanguage', () => {
  it('DELETEs the language and invalidates the languages query', async () => {
    del.mockReturnValue(ok(undefined, 204));
    const { queryClient, wrapper } = makeClient();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useRemoveLanguage(), { wrapper });
    await result.current.mutateAsync(1);

    expect(del).toHaveBeenCalledWith('/languages/{language_id}', {
      params: { path: { language_id: 1 } },
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['languages'] });
  });
});
