import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Mock only `getApiClient`; keep the real `unwrap`/`ApiError` so the typed result + error paths run.
const { get, del } = vi.hoisted(() => ({ get: vi.fn(), del: vi.fn() }));
vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, getApiClient: () => ({ GET: get, DELETE: del }) };
});

import { ApiError } from '@/lib/api-client';
import {
  ACCOUNT_EXPORT_FILENAME,
  DELETE_CONFIRM_PHRASE,
  downloadJson,
  useDeleteAccount,
  useExportAccount,
} from '@/lib/account';

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

/** Read a Blob as text via FileReader (jsdom's Blob has no `.text()`). */
function readBlobText(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

const EXPORT_BUNDLE = {
  profile: { id: 'u1', plan: 'free', created_at: '2026-01-01T00:00:00Z' },
  languages: [
    {
      id: 1,
      name: 'Spanish',
      code: 'es',
      vowelized: false,
      created_at: '2026-01-01T00:00:00Z',
    },
  ],
  cards: [],
  reviews: [],
  proficiency: [],
  settings: { discover_count: '7' },
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('account constants', () => {
  it('names the export file and the delete confirmation phrase', () => {
    expect(ACCOUNT_EXPORT_FILENAME).toBe('lengua-export.json');
    expect(DELETE_CONFIRM_PHRASE).toBe('delete my account');
  });
});

describe('useExportAccount', () => {
  it('GETs /account/export and returns the typed bundle', async () => {
    get.mockReturnValue(ok(EXPORT_BUNDLE));
    const { result } = renderHook(() => useExportAccount(), {
      wrapper: makeWrapper(),
    });

    const bundle = await result.current.mutateAsync();
    expect(get).toHaveBeenCalledWith('/account/export');
    expect(bundle).toEqual(EXPORT_BUNDLE);
  });
});

describe('useDeleteAccount', () => {
  it('DELETEs /account and resolves to void on 204', async () => {
    del.mockReturnValue(ok(undefined, 204));
    const { result } = renderHook(() => useDeleteAccount(), {
      wrapper: makeWrapper(),
    });

    await expect(result.current.mutateAsync()).resolves.toBeUndefined();
    expect(del).toHaveBeenCalledWith('/account');
    expect(del).toHaveBeenCalledTimes(1);
  });

  it('throws a typed retryable ApiError for the partial-failure 502', async () => {
    del.mockReturnValue(
      Promise.resolve({
        data: undefined,
        error: {
          detail: 'Account deletion failed; no data was removed. Please retry.',
        },
        response: new Response(null, { status: 502 }),
      }),
    );
    const { result } = renderHook(() => useDeleteAccount(), {
      wrapper: makeWrapper(),
    });

    await expect(result.current.mutateAsync()).rejects.toMatchObject({
      status: 502,
      message: 'Account deletion failed; no data was removed. Please retry.',
    });
    await expect(result.current.mutateAsync()).rejects.toBeInstanceOf(ApiError);
  });
});

describe('downloadJson', () => {
  let click: ReturnType<typeof vi.spyOn>;
  let captured: { download: string; href: string | null } | null;
  const createObjectURL = vi.fn<(obj: Blob | MediaSource) => string>(
    () => 'blob:fake',
  );
  const revokeObjectURL = vi.fn<(url: string) => void>();

  beforeEach(() => {
    captured = null;
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = revokeObjectURL;
    // Capture the anchor's attributes at click time (it is removed right after), without aliasing
    // `this` to a variable (lint: no-this-alias).
    click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(function (this: HTMLAnchorElement) {
        captured = { download: this.download, href: this.getAttribute('href') };
      });
  });

  afterEach(() => {
    click.mockRestore();
  });

  it('serializes the data, clicks a hidden anchor, and revokes the URL on the NEXT tick', async () => {
    downloadJson('lengua-export.json', EXPORT_BUNDLE);

    // A JSON blob was created and offered via a download anchor pointing at the object URL…
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    const blob = createObjectURL.mock.calls[0][0] as unknown as Blob;
    expect(blob.type).toBe('application/json');
    expect(click).toHaveBeenCalledTimes(1);
    expect(captured).not.toBeNull();
    expect(captured?.download).toBe('lengua-export.json');
    expect(captured?.href).toBe('blob:fake');

    // The anchor is cleaned up immediately, but the URL is NOT revoked synchronously — revoking in
    // the same tick can abort the download in async-download browsers (Safari/Firefox).
    expect(document.querySelector('a[download]')).toBeNull();
    expect(revokeObjectURL).not.toHaveBeenCalled();

    // The blob carries the exact export payload.
    expect(JSON.parse(await readBlobText(blob))).toEqual(EXPORT_BUNDLE);

    // …and the object URL is revoked on the next macrotask (no leak).
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:fake');
  });
});
