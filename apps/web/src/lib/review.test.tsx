import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock only `getApiClient`; keep the real `unwrap`/`ApiError` so the typed result path is exercised.
const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, getApiClient: () => ({ GET: get, POST: post }) };
});
// Spy the activation-funnel event so we can assert it fires on a successful grade (5.9.2).
const { trackReview } = vi.hoisted(() => ({ trackReview: vi.fn() }));
vi.mock('@/lib/analytics-events', () => ({ trackReview }));

import {
  bareWord,
  cardExplanation,
  dueKey,
  explainKey,
  isProductionCard,
  ratingButtonClass,
  ratingFlashClass,
  RATINGS,
  segmentSentence,
  useDueQuery,
  useExplainWord,
  useGradeCard,
  type RatingColor,
} from '@/lib/review';

/** An openapi-fetch-shaped success result the real `unwrap` accepts. */
function ok<T>(data: T, status = 200) {
  return Promise.resolve({
    data,
    error: undefined,
    response: new Response(null, { status }),
  });
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

describe('isProductionCard', () => {
  it('is true only for the production direction', () => {
    expect(isProductionCard({ direction: 'production' })).toBe(true);
    expect(isProductionCard({ direction: 'recognition' })).toBe(false);
    // Legacy/imported cards without a direction are treated as recognition.
    expect(isProductionCard({ direction: null })).toBe(false);
  });
});

describe('RATINGS (locked FSRS colours)', () => {
  it('maps Again/Hard/Good/Easy to grades 1–4 and red/orange/blue/green in order', () => {
    expect(RATINGS.map((r) => [r.value, r.label, r.color])).toEqual([
      [1, 'Again', 'red'],
      [2, 'Hard', 'orange'],
      [3, 'Good', 'blue'],
      [4, 'Easy', 'green'],
    ]);
  });
});

describe('ratingButtonClass', () => {
  it('returns the locked tinted-pill treatment for each colour (soft fill + deep text)', () => {
    const cases: Record<RatingColor, string> = {
      red: 'bg-hig-red/15 text-hig-red-deep border-hig-red/25 hover:bg-hig-red/25',
      orange:
        'bg-hig-orange/15 text-hig-orange-deep border-hig-orange/25 hover:bg-hig-orange/25',
      blue: 'bg-hig-blue/15 text-hig-blue-deep border-hig-blue/25 hover:bg-hig-blue/25',
      green:
        'bg-hig-green/15 text-hig-green-deep border-hig-green/25 hover:bg-hig-green/25',
    };
    for (const [color, expected] of Object.entries(cases)) {
      expect(ratingButtonClass(color as RatingColor)).toBe(expected);
    }
  });
});

describe('ratingFlashClass', () => {
  it('fills the committed pill solid in its vivid hue for each colour', () => {
    const cases: Record<RatingColor, string> = {
      red: 'bg-hig-red text-white border-transparent',
      orange: 'bg-hig-orange text-white border-transparent',
      blue: 'bg-hig-blue text-white border-transparent',
      green: 'bg-hig-green text-white border-transparent',
    };
    for (const [color, expected] of Object.entries(cases)) {
      expect(ratingFlashClass(color as RatingColor)).toBe(expected);
    }
  });
});

describe('bareWord', () => {
  it('strips surrounding punctuation but keeps inner characters and diacritics', () => {
    expect(bareWord('estás?')).toBe('estás');
    expect(bareWord('estás.')).toBe('estás');
    expect(bareWord('"hola,"')).toBe('hola');
    expect(bareWord('gato')).toBe('gato');
  });

  it('mirrors the backend STRIP_CHARS exactly (¿/¡ are NOT stripped) so cache keys match', () => {
    // The backend `lengua_core.cards.bare_word` does not strip the inverted marks; the client must
    // strip identically or a stored-explanation lookup would miss. `?` trails off, `¿` stays.
    expect(bareWord('¿cómo?')).toBe('¿cómo');
  });

  it('strips the Arabic comma/question marks too', () => {
    expect(bareWord('كتاب،')).toBe('كتاب');
  });

  it('returns an empty string for pure punctuation', () => {
    expect(bareWord('—')).toBe('—'); // an em dash is not in STRIP_CHARS
    expect(bareWord('...')).toBe('');
    expect(bareWord('')).toBe('');
  });
});

describe('segmentSentence', () => {
  it('splits into tappable words + verbatim separators, preserving the exact text', () => {
    const segments = segmentSentence('Hola, ¿cómo estás?');
    expect(segments.map((s) => s.raw).join('')).toBe('Hola, ¿cómo estás?');
    const words = segments.filter((s) => s.isWord);
    // `¿` is kept (matches the backend bare_word); `,` and `?` are stripped.
    expect(words.map((s) => s.bare)).toEqual(['Hola', '¿cómo', 'estás']);
  });

  it('marks pure-punctuation tokens as non-words', () => {
    const segments = segmentSentence('hola ... mundo');
    const words = segments.filter((s) => s.isWord).map((s) => s.bare);
    expect(words).toEqual(['hola', 'mundo']);
  });

  it('returns an empty list for an empty sentence', () => {
    expect(segmentSentence('')).toEqual([]);
  });

  it('returns correct word spans for an RTL string, keeping diacritics in the bare form (4.9.4)', () => {
    // Hebrew "שָׁלוֹם עוֹלָם גָּדוֹל" (with nikkud) — three whitespace-separated words.
    const input = 'שָׁלוֹם עוֹלָם גָּדוֹל';
    const segments = segmentSentence(input);
    // Reconstruction is exact (so click/touch targets line up with the source).
    expect(segments.map((s) => s.raw).join('')).toBe(input);
    const words = segments.filter((s) => s.isWord);
    expect(words).toHaveLength(3);
    // The nikkud is retained in the bare form (it keys the explanation cache).
    expect(words.map((s) => s.bare)).toEqual(['שָׁלוֹם', 'עוֹלָם', 'גָּדוֹל']);
  });

  it('strips Arabic punctuation but keeps Arabic harakat in the bare form', () => {
    // "بيتٌ، كبيرٌ" — the Arabic comma (،, in STRIP_CHARS) is stripped; the dammatan (ٌ) is kept.
    const words = segmentSentence('بيتٌ، كبيرٌ')
      .filter((s) => s.isWord)
      .map((s) => s.bare);
    expect(words).toEqual(['بيتٌ', 'كبيرٌ']);
  });
});

describe('cardExplanation', () => {
  it('returns the stored note for a word when it is a string', () => {
    expect(cardExplanation({ casa: 'house' }, 'casa')).toBe('house');
  });

  it('returns undefined for a missing word, null map, or non-string note', () => {
    expect(cardExplanation({ casa: 'house' }, 'perro')).toBeUndefined();
    expect(cardExplanation(null, 'casa')).toBeUndefined();
    expect(cardExplanation(undefined, 'casa')).toBeUndefined();
    expect(cardExplanation({ casa: 42 }, 'casa')).toBeUndefined();
  });
});

describe('query keys', () => {
  it('dueKey lives under the shared review prefix', () => {
    expect(dueKey(7)).toEqual(['review', 'due', 7]);
  });

  it('explainKey is keyed by word + language', () => {
    expect(explainKey(3, 'casa')).toEqual(['explain', 3, 'casa']);
  });
});

describe('useDueQuery', () => {
  it('GETs /review/due with the language id and returns the split batch', async () => {
    const batch = { new: [{ id: 1 }], due: [{ id: 2 }] };
    get.mockReturnValue(ok(batch));
    const { wrapper } = makeClient();

    const { result } = renderHook(() => useDueQuery(5), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(get).toHaveBeenCalledWith('/review/due', {
      params: { query: { language_id: 5 } },
    });
    expect(result.current.data).toEqual(batch);
  });

  it('is disabled (no request) when there is no active language', () => {
    const { wrapper } = makeClient();
    renderHook(() => useDueQuery(null), { wrapper });
    expect(get).not.toHaveBeenCalled();
  });
});

describe('useGradeCard', () => {
  it('POSTs the FSRS rating to /review/{card_id}/grade', async () => {
    const outcome = {
      card_id: 9,
      due: '2026-07-01T00:00:00Z',
      score: 1.5,
      score_changed: true,
    };
    post.mockReturnValue(ok(outcome));
    const { wrapper } = makeClient();

    const { result } = renderHook(() => useGradeCard(), { wrapper });
    const out = await result.current.mutateAsync({ cardId: 9, rating: 3 });

    expect(post).toHaveBeenCalledWith('/review/{card_id}/grade', {
      params: { path: { card_id: 9 } },
      body: { rating: 3 },
    });
    expect(out).toEqual(outcome);
    // Funnel event fires with only the 1..4 rating (no PII).
    expect(trackReview).toHaveBeenCalledWith(3);
  });
});

describe('useExplainWord', () => {
  const params = {
    languageId: 2,
    word: 'silla',
    sentence: 'El gato duerme en la silla.',
    translation: 'The cat sleeps on the chair.',
  };

  it('POSTs /explain with word + sentence + translation and caches under the word+language key', async () => {
    post.mockReturnValue(ok({ word: 'silla', explanation: 'a chair' }));
    const { queryClient, wrapper } = makeClient();

    const { result } = renderHook(() => useExplainWord(params), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(post).toHaveBeenCalledWith('/explain', {
      body: {
        language_id: 2,
        word: 'silla',
        sentence: 'El gato duerme en la silla.',
        translation: 'The cat sleeps on the chair.',
      },
    });
    expect(result.current.data?.explanation).toBe('a chair');
    // Cached under the word + language key.
    expect(queryClient.getQueryData(explainKey(2, 'silla'))).toMatchObject({
      explanation: 'a chair',
    });
  });

  it('uses a pre-generated card note as initial data without any request', async () => {
    const { result } = renderHook(
      () => useExplainWord(params, 'pre-generated note'),
      { wrapper: makeClient().wrapper },
    );
    expect(result.current.data?.explanation).toBe('pre-generated note');
    expect(post).not.toHaveBeenCalled();
  });

  it('is disabled (no request) when no word is selected', () => {
    renderHook(() => useExplainWord(null), { wrapper: makeClient().wrapper });
    expect(post).not.toHaveBeenCalled();
  });
});
