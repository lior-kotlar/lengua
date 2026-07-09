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
// Spy the activation-funnel event so we can assert it fires on a successful add (5.9.2).
const { trackLanguageAdded } = vi.hoisted(() => ({
  trackLanguageAdded: vi.fn(),
}));
vi.mock('@/lib/analytics-events', () => ({ trackLanguageAdded }));

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
    post.mockReturnValue(ok({ ...SPANISH, created: true }));
    const { queryClient, wrapper } = makeClient();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useAddLanguage(), { wrapper });
    const outcome = await result.current.mutateAsync({
      name: '  Spanish  ',
      code: '  es  ',
      vowelized: true,
    });

    // The `created` flag is split off — `language` is the plain LanguageOut.
    expect(outcome).toEqual({
      language: SPANISH,
      created: true,
      bandError: false,
    });
    expect(post).toHaveBeenCalledWith('/languages', {
      body: { name: 'Spanish', code: 'es', vowelized: true },
    });
    // Default band (no band given) → no proficiency PUT.
    expect(put).not.toHaveBeenCalled();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['languages'] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['proficiency', 1] });
    // Funnel event fires with the (non-PII) language code from the created row, plus whether the
    // name is a curated pick (#95) — "Spanish" is in the curated list, so `curated: true`.
    expect(trackLanguageAdded).toHaveBeenCalledWith('es', true);
  });

  it('omits the code when blank and defaults vowelized to false', async () => {
    // The created row also has a null code → the funnel event passes null through (not undefined).
    post.mockReturnValue(ok({ ...SPANISH, code: null, created: true }));
    const { wrapper } = makeClient();

    const { result } = renderHook(() => useAddLanguage(), { wrapper });
    await result.current.mutateAsync({ name: 'Spanish' });

    expect(post).toHaveBeenCalledWith('/languages', {
      body: { name: 'Spanish', code: null, vowelized: false },
    });
    expect(trackLanguageAdded).toHaveBeenCalledWith(null, true);
  });

  it('reports curated:false for a name that is not in the curated list', async () => {
    // A custom/experimental language (not in the curated table) → the funnel event marks it uncurated.
    post.mockReturnValue(
      ok({
        id: 7,
        name: 'Klingon',
        code: 'tlh',
        vowelized: false,
        created: true,
      }),
    );
    const { wrapper } = makeClient();

    const { result } = renderHook(() => useAddLanguage(), { wrapper });
    await result.current.mutateAsync({ name: 'Klingon', code: 'tlh' });

    expect(trackLanguageAdded).toHaveBeenCalledWith('tlh', false);
  });

  it('PUTs the starting band when it is not the default A1 (newly created)', async () => {
    post.mockReturnValue(ok({ ...SPANISH, id: 9, created: true }));
    put.mockReturnValue(ok({ band: 'B1', progress: 0, score: 2 }));
    const { wrapper } = makeClient();

    const { result } = renderHook(() => useAddLanguage(), { wrapper });
    const outcome = await result.current.mutateAsync({
      name: 'French',
      band: 'B1',
    });

    expect(put).toHaveBeenCalledWith('/proficiency/{language_id}', {
      params: { path: { language_id: 9 } },
      body: { band: 'B1' },
    });
    expect(outcome.created).toBe(true);
    expect(outcome.bandError).toBe(false);
  });

  it('does not PUT proficiency for the default A1 starting band', async () => {
    post.mockReturnValue(ok({ ...SPANISH, created: true }));
    const { wrapper } = makeClient();

    const { result } = renderHook(() => useAddLanguage(), { wrapper });
    await result.current.mutateAsync({ name: 'Spanish', band: 'A1' });

    expect(put).not.toHaveBeenCalled();
  });

  it('S3: re-adding an existing language (created=false) skips the band PUT and the funnel event', async () => {
    // Idempotent add: the backend returns the EXISTING row with `created: false`. Even with a
    // non-default starting band chosen, the proficiency must NOT be reset.
    post.mockReturnValue(ok({ ...SPANISH, id: 7, created: false }));
    const { queryClient, wrapper } = makeClient();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useAddLanguage(), { wrapper });
    const outcome = await result.current.mutateAsync({
      name: 'Spanish',
      band: 'B2',
    });

    expect(outcome).toEqual({
      language: { ...SPANISH, id: 7 },
      created: false,
      bandError: false,
    });
    // No proficiency reset, and no activation-funnel event for a re-add.
    expect(put).not.toHaveBeenCalled();
    expect(trackLanguageAdded).not.toHaveBeenCalled();
    // The list is still invalidated so the (existing) language is reflected everywhere.
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['languages'] });
  });

  it('S12: a failed band PUT still resolves the add (bandError) and invalidates the list', async () => {
    post.mockReturnValue(ok({ ...SPANISH, id: 9, created: true }));
    // The band PUT fails (e.g. transient 500) AFTER the language was created.
    put.mockReturnValue(
      Promise.resolve({
        data: undefined,
        error: { detail: 'boom' },
        response: new Response(null, { status: 500 }),
      }),
    );
    const { queryClient, wrapper } = makeClient();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useAddLanguage(), { wrapper });
    const outcome = await result.current.mutateAsync({
      name: 'French',
      band: 'B1',
    });

    // The add resolves (does not reject) because the language WAS created.
    expect(outcome.created).toBe(true);
    expect(outcome.bandError).toBe(true);
    expect(outcome.language).toEqual({ ...SPANISH, id: 9 });
    // The list is invalidated so the created language appears despite the band failure.
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['languages'] });
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
