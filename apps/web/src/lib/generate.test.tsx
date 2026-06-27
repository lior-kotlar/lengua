import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock only `getApiClient`; keep the real `unwrap`/`ApiError` so the typed result path is exercised.
const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, getApiClient: () => ({ POST: post }) };
});

import {
  cardsForSentences,
  groupSentences,
  parseWords,
  useGenerate,
  useSaveCards,
  WORDS_PER_REQUEST_CAP,
  type GeneratedCard,
} from '@/lib/generate';

/** An openapi-fetch-shaped success result the real `unwrap` accepts. */
function ok<T>(data: T, status = 200) {
  return Promise.resolve({
    data,
    error: undefined,
    response: new Response(null, { status }),
  });
}

function recognition(
  sentence: string,
  translation: string,
  used: string[],
): GeneratedCard {
  return {
    direction: 'recognition',
    front: sentence,
    back: translation,
    used_words: used,
    word_explanations: null,
    gen_level: null,
  };
}

function production(
  sentence: string,
  translation: string,
  used: string[],
): GeneratedCard {
  return {
    direction: 'production',
    front: translation,
    back: sentence,
    used_words: used,
    word_explanations: { [used[0]]: 'note' },
    gen_level: null,
  };
}

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

describe('parseWords', () => {
  it('splits on newlines and commas, trims, and drops blanks', () => {
    expect(parseWords(' casa\n perro , gato ,,\n\n')).toEqual([
      'casa',
      'perro',
      'gato',
    ]);
  });

  it('keeps multi-word phrases intact (does not split on spaces)', () => {
    expect(parseWords('buenos días\nhola')).toEqual(['buenos días', 'hola']);
  });

  it('returns an empty list for blank input', () => {
    expect(parseWords('   \n , \n ')).toEqual([]);
  });
});

describe('WORDS_PER_REQUEST_CAP', () => {
  it('is sourced from the generated schema constant (GenerateRequest.words.maxItems)', () => {
    expect(WORDS_PER_REQUEST_CAP).toBe(30);
  });
});

describe('groupSentences', () => {
  it('pairs a recognition + production card into one sentence', () => {
    const groups = groupSentences([
      recognition('S1', 'T1', ['a']),
      production('S1', 'T1', ['a']),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0]).toMatchObject({
      key: 'S1',
      sentence: 'S1',
      translation: 'T1',
      usedWords: ['a'],
    });
    expect(groups[0].cards).toHaveLength(2);
  });

  it('orients correctly when the production card arrives first', () => {
    const groups = groupSentences([
      production('S', 'T', ['a']),
      recognition('S', 'T', ['a']),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].sentence).toBe('S');
    expect(groups[0].translation).toBe('T');
  });

  it('keeps distinct sentences separate and preserves order', () => {
    const groups = groupSentences([
      recognition('S1', 'T1', ['a']),
      production('S1', 'T1', ['a']),
      recognition('S2', 'T2', ['b']),
      production('S2', 'T2', ['b']),
    ]);
    expect(groups.map((g) => g.key)).toEqual(['S1', 'S2']);
  });

  it('returns an empty list for no cards', () => {
    expect(groupSentences([])).toEqual([]);
  });
});

describe('cardsForSentences', () => {
  it('flattens the cards of the given sentences', () => {
    const groups = groupSentences([
      recognition('S1', 'T1', ['a']),
      production('S1', 'T1', ['a']),
    ]);
    expect(cardsForSentences(groups)).toHaveLength(2);
    expect(cardsForSentences([])).toEqual([]);
  });
});

describe('useGenerate', () => {
  it('POSTs /generate with the language id + words and returns the cards', async () => {
    const cards = [recognition('S', 'T', ['a']), production('S', 'T', ['a'])];
    post.mockReturnValue(ok(cards));
    const { wrapper } = makeClient();

    const { result } = renderHook(() => useGenerate(), { wrapper });
    const out = await result.current.mutateAsync({
      languageId: 3,
      words: ['a'],
    });

    expect(post).toHaveBeenCalledWith('/generate', {
      body: { language_id: 3, words: ['a'] },
    });
    expect(out).toEqual(cards);
  });

  it('surfaces a typed ApiError for a non-2xx response', async () => {
    post.mockReturnValue(
      Promise.resolve({
        data: undefined,
        error: { code: 'daily_cap_reached', message: 'Daily limit reached.' },
        response: new Response(null, { status: 429 }),
      }),
    );
    const { wrapper } = makeClient();

    const { result } = renderHook(() => useGenerate(), { wrapper });
    await expect(
      result.current.mutateAsync({ languageId: 1, words: ['a'] }),
    ).rejects.toMatchObject({ status: 429, code: 'daily_cap_reached' });
  });
});

describe('useSaveCards', () => {
  it('POSTs /cards/save with exactly the given cards and invalidates the review cache', async () => {
    const saved = [{ id: 1 }];
    post.mockReturnValue(ok(saved));
    const { queryClient, wrapper } = makeClient();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    const cards = [recognition('S', 'T', ['a']), production('S', 'T', ['a'])];

    const { result } = renderHook(() => useSaveCards(), { wrapper });
    const out = await result.current.mutateAsync({ languageId: 7, cards });

    expect(post).toHaveBeenCalledWith('/cards/save', {
      body: { language_id: 7, cards },
    });
    expect(out).toEqual(saved);
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ['review'] }),
    );
  });
});
