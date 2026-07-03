import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock only `getApiClient`; keep the real `unwrap` so the typed result path is exercised end to end.
const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, getApiClient: () => ({ GET: get }) };
});

import {
  buildLanguageTiles,
  dueTotals,
  formatDayLine,
  greetingForHour,
  useDashboardTiles,
  type TileQueryResult,
} from '@/lib/dashboard';
import type { LanguageOut } from '@/lib/languages';
import type { ProficiencyOut } from '@/lib/proficiency';
import type { DueResponse } from '@/lib/review';

const SPANISH: LanguageOut = {
  id: 1,
  name: 'Spanish',
  code: 'es',
  vowelized: false,
};
const HEBREW: LanguageOut = {
  id: 3,
  name: 'Hebrew',
  code: 'he',
  vowelized: true,
};

function ok<T>(data: T) {
  return Promise.resolve({
    data,
    error: undefined,
    response: new Response(null, { status: 200 }),
  });
}

function makeCards(count: number): DueResponse['due'] {
  return Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    language_id: 1,
    direction: 'recognition',
    front: 'f',
    back: 'b',
    used_words: null,
    word_explanations: null,
    gen_level: null,
    saved: true,
    due: null,
  }));
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('greetingForHour', () => {
  it('maps each hour band to its greeting', () => {
    expect(greetingForHour(0)).toBe('Good night');
    expect(greetingForHour(4)).toBe('Good night');
    expect(greetingForHour(5)).toBe('Good morning');
    expect(greetingForHour(11)).toBe('Good morning');
    expect(greetingForHour(12)).toBe('Good afternoon');
    expect(greetingForHour(16)).toBe('Good afternoon');
    expect(greetingForHour(17)).toBe('Good evening');
    expect(greetingForHour(21)).toBe('Good evening');
    expect(greetingForHour(22)).toBe('Good night');
    expect(greetingForHour(23)).toBe('Good night');
  });
});

describe('formatDayLine', () => {
  it('formats a date as weekday, month day (en-US)', () => {
    // 2026-07-02 is a Thursday.
    expect(formatDayLine(new Date(2026, 6, 2))).toBe('Thursday, July 2');
    expect(formatDayLine(new Date(2026, 0, 1))).toBe('Thursday, January 1');
  });
});

describe('dueTotals', () => {
  it('splits a due batch into due / fresh / total', () => {
    const response: DueResponse = { due: makeCards(2), new: makeCards(3) };
    expect(dueTotals(response)).toEqual({ due: 2, fresh: 3, total: 5 });
  });

  it('is all-zero for an undefined payload (still loading)', () => {
    expect(dueTotals(undefined)).toEqual({ due: 0, fresh: 0, total: 0 });
  });

  it('handles an empty batch', () => {
    expect(dueTotals({ due: [], new: [] })).toEqual({
      due: 0,
      fresh: 0,
      total: 0,
    });
  });
});

describe('buildLanguageTiles', () => {
  const languages = [SPANISH, HEBREW];

  it('derives tile models, marking the active language and its due/band state', () => {
    const dueResults: TileQueryResult<DueResponse>[] = [
      {
        data: { due: makeCards(1), new: makeCards(2) },
        isPending: false,
        isError: false,
      },
      { data: { due: [], new: [] }, isPending: false, isError: false },
    ];
    const profResults: TileQueryResult<ProficiencyOut>[] = [
      {
        data: { band: 'B1', progress: 0.4, score: 2.4 },
        isPending: false,
        isError: false,
      },
      {
        data: { band: 'A1', progress: 0.1, score: 0.2 },
        isPending: false,
        isError: false,
      },
    ];

    const tiles = buildLanguageTiles(languages, 1, dueResults, profResults);

    expect(tiles[0]).toMatchObject({
      language: SPANISH,
      isActive: true,
      totals: { due: 1, fresh: 2, total: 3 },
      dueLoading: false,
      band: 'B1',
      progress: 0.4,
    });
    expect(tiles[1]).toMatchObject({
      language: HEBREW,
      isActive: false,
      totals: { due: 0, fresh: 0, total: 0 },
      band: 'A1',
    });
  });

  it('degrades gracefully while a tile is loading or its level errored', () => {
    const dueResults: TileQueryResult<DueResponse>[] = [
      { data: undefined, isPending: true, isError: false },
      {
        data: { due: makeCards(1), new: [] },
        isPending: false,
        isError: false,
      },
    ];
    const profResults: TileQueryResult<ProficiencyOut>[] = [
      { data: undefined, isPending: true, isError: false },
      { data: undefined, isPending: false, isError: true },
    ];

    const tiles = buildLanguageTiles(languages, null, dueResults, profResults);

    // Loading tile: no totals yet, dueLoading true, not errored, no band.
    expect(tiles[0].totals).toBeNull();
    expect(tiles[0].dueLoading).toBe(true);
    expect(tiles[0].dueError).toBe(false);
    expect(tiles[0].band).toBeNull();
    expect(tiles[0].progress).toBe(0);
    expect(tiles[0].isActive).toBe(false);
    // Errored-level tile: due batch resolved, but band degrades to null.
    expect(tiles[1].totals).toEqual({ due: 1, fresh: 0, total: 1 });
    expect(tiles[1].band).toBeNull();
  });

  it('flags a tile whose due batch errored (settled, not loading)', () => {
    const dueResults: TileQueryResult<DueResponse>[] = [
      { data: undefined, isPending: false, isError: true },
      { data: { due: [], new: [] }, isPending: false, isError: false },
    ];
    const profResults: TileQueryResult<ProficiencyOut>[] = [
      {
        data: { band: 'B1', progress: 0.5, score: 2 },
        isPending: false,
        isError: false,
      },
      {
        data: { band: 'A1', progress: 0, score: 0 },
        isPending: false,
        isError: false,
      },
    ];

    const tiles = buildLanguageTiles(languages, 1, dueResults, profResults);

    // Errored due batch → no totals, NOT loading, dueError true (so the badge degrades, not shimmers).
    expect(tiles[0].totals).toBeNull();
    expect(tiles[0].dueLoading).toBe(false);
    expect(tiles[0].dueError).toBe(true);
    // The healthy tile is unaffected.
    expect(tiles[1].dueError).toBe(false);
    expect(tiles[1].totals).toEqual({ due: 0, fresh: 0, total: 0 });
  });
});

describe('useDashboardTiles', () => {
  function wrapper({ children }: { children: React.ReactNode }) {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  }

  it('fans out the due batch + proficiency for every language into tile models', async () => {
    get.mockImplementation(
      (
        path: string,
        opts: {
          params: {
            query?: { language_id: number };
            path?: { language_id: number };
          };
        },
      ) => {
        if (path === '/review/due') {
          const id = opts.params.query!.language_id;
          return ok(
            id === 1
              ? { due: makeCards(2), new: makeCards(1) }
              : { due: [], new: [] },
          );
        }
        if (path === '/proficiency/{language_id}') {
          const id = opts.params.path!.language_id;
          return ok(
            id === 1
              ? { band: 'B2', progress: 0.6, score: 3 }
              : { band: 'A1', progress: 0, score: 0 },
          );
        }
        throw new Error(`unexpected path ${path}`);
      },
    );

    const { result } = renderHook(
      () => useDashboardTiles([SPANISH, HEBREW], 1),
      {
        wrapper,
      },
    );

    await waitFor(() => expect(result.current[0]?.totals?.total).toBe(3));

    expect(result.current[0]).toMatchObject({
      isActive: true,
      totals: { due: 2, fresh: 1, total: 3 },
      band: 'B2',
    });
    expect(result.current[1]).toMatchObject({
      isActive: false,
      totals: { due: 0, fresh: 0, total: 0 },
      band: 'A1',
    });
    // Reuses the shared fetchers → one due request + one proficiency request per language.
    expect(get).toHaveBeenCalledWith('/review/due', {
      params: { query: { language_id: 1 } },
    });
    expect(get).toHaveBeenCalledWith('/proficiency/{language_id}', {
      params: { path: { language_id: 3 } },
    });
  });

  it('returns no tiles for an empty language list (no requests)', () => {
    const { result } = renderHook(() => useDashboardTiles([], null), {
      wrapper,
    });
    expect(result.current).toEqual([]);
    expect(get).not.toHaveBeenCalled();
  });
});
