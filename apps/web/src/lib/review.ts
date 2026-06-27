/**
 * Review / FSRS-loop data layer — TanStack Query hooks over the typed API client, plus the pure
 * helpers the Review screen (group 4.6) builds on. Ported from the legacy Streamlit review page.
 *
 * The loop: `GET /review/due` returns today's batch split into never-reviewed (`new`) vs. `due`
 * cards; the user reveals each card's answer and rates it Again/Hard/Good/Easy, which `POST`s an
 * FSRS rating (1..4) to `/review/{card_id}/grade` and advances. On production cards, tapping a word
 * fetches a short explanation via `POST /explain` (cached per word). Everything goes through
 * `getApiClient()` (auth + 401-retry) and `unwrap()` (typed data / typed
 * {@link import('@/lib/api-client').ApiError}); Supabase is auth-only.
 */
import { useMutation, useQuery } from '@tanstack/react-query';
import type { components } from 'api-types';

import { getApiClient, unwrap } from '@/lib/api-client';

/** A persisted flashcard row returned by `GET /review/due`. */
export type CardOut = components['schemas']['CardOut'];

/** The due batch for a language, split into never-reviewed (`new`) vs. `due` cards. */
export type DueResponse = components['schemas']['DueResponse'];

/** The outcome of grading a card (`POST /review/{card_id}/grade`). */
export type GradeResponse = components['schemas']['GradeResponse'];

/** A short explanation of a tapped word (`POST /explain`). */
export type ExplainResponse = components['schemas']['ExplainResponse'];

/**
 * The two directions a sentence is studied in (mirror `lengua_core.cards`):
 * - recognition — front = target sentence, back = English (reading);
 * - production — front = English, back = target sentence (build it yourself), with tap-a-word.
 * Legacy/imported cards may have a `null` direction; those are treated as recognition.
 */
export const RECOGNITION = 'recognition';
export const PRODUCTION = 'production';

/** True for a production card (English prompt → build the target sentence; renders tap-a-word). */
export function isProductionCard(card: Pick<CardOut, 'direction'>): boolean {
  return card.direction === PRODUCTION;
}

// ── FSRS ratings — LOCKED colours ────────────────────────────────────────────────────────────────
//
// The four ratings map to FSRS grades 1..4 and their colours are a LOCKED product decision:
// Again = red, Hard = orange, Good = blue, Easy = green. The constant below is the single source of
// truth shared by the rating buttons and the keyboard shortcuts (digits 1..4), so the order, grade
// value and colour never drift apart.

/** The locked colour of a rating button. */
export type RatingColor = 'red' | 'orange' | 'blue' | 'green';

/** One FSRS rating: its grade value (1..4 — also its keyboard digit), label and locked colour. */
export interface ReviewRating {
  value: 1 | 2 | 3 | 4;
  label: 'Again' | 'Hard' | 'Good' | 'Easy';
  color: RatingColor;
}

/** The four FSRS ratings in ascending order, with their LOCKED colours. */
export const RATINGS: readonly ReviewRating[] = [
  { value: 1, label: 'Again', color: 'red' },
  { value: 2, label: 'Hard', color: 'orange' },
  { value: 3, label: 'Good', color: 'blue' },
  { value: 4, label: 'Easy', color: 'green' },
] as const;

/**
 * Tailwind background (+ hover) classes for a rating button, by its locked colour.
 *
 * Kept as an exhaustive switch (no `default`) so adding a colour is a type error rather than a
 * silent fallthrough, and so every branch is covered. Uses the same red/orange/blue/green family as
 * the rest of the app.
 */
export function ratingButtonClass(color: RatingColor): string {
  switch (color) {
    case 'red':
      return 'bg-red-500 hover:bg-red-600';
    case 'orange':
      return 'bg-orange-500 hover:bg-orange-600';
    case 'blue':
      return 'bg-blue-500 hover:bg-blue-600';
    case 'green':
      return 'bg-green-500 hover:bg-green-600';
  }
}

// ── Tap-a-word segmentation ──────────────────────────────────────────────────────────────────────

/**
 * Punctuation trimmed off a token to get its "bare" word. Mirrors `lengua_core.cards.STRIP_CHARS`
 * (including the Arabic `؟،؛` marks) so the word the client taps matches the key the backend stored
 * its explanation under — otherwise a cached lookup would miss.
 */
export const STRIP_CHARS = '.,!?؟،؛:;"\'«»…()[]';

/** The token with surrounding punctuation stripped (diacritics kept) — `lengua_core.cards.bare_word`. */
export function bareWord(token: string): string {
  let start = 0;
  let end = token.length;
  while (start < end && STRIP_CHARS.includes(token[start])) {
    start += 1;
  }
  while (end > start && STRIP_CHARS.includes(token[end - 1])) {
    end -= 1;
  }
  return token.slice(start, end);
}

/** One piece of a segmented sentence: a tappable word, or inter-word text (spaces/punctuation). */
export interface SentenceSegment {
  /** The exact source text of this segment (rendered verbatim so spacing is preserved). */
  raw: string;
  /** The bare word to explain (empty for non-word segments). */
  bare: string;
  /** Whether this segment is a tappable word. */
  isWord: boolean;
}

/**
 * Split a sentence into ordered segments for tap-a-word rendering.
 *
 * Tokens are separated on whitespace (so the clickable unit matches the backend's whitespace split),
 * and the whitespace runs are kept as their own non-word segments so the sentence renders with its
 * exact spacing. A token that is pure punctuation (empty bare form) is non-tappable. Concatenating
 * every `raw` reproduces the input, so word boundaries are exact on both touch and click.
 */
export function segmentSentence(text: string): SentenceSegment[] {
  return text
    .split(/(\s+)/)
    .filter((chunk) => chunk !== '')
    .map((chunk) => {
      if (/^\s+$/.test(chunk)) {
        return { raw: chunk, bare: '', isWord: false };
      }
      const bare = bareWord(chunk);
      return { raw: chunk, bare, isWord: bare !== '' };
    });
}

// ── Queries & mutations ──────────────────────────────────────────────────────────────────────────

/**
 * Query key for a language's due batch. Lives under the shared `['review', ...]` prefix that
 * `useSaveCards` (group 4.5) invalidates, so saving new cards refreshes the review queue.
 */
export function dueKey(languageId: number) {
  return ['review', 'due', languageId] as const;
}

/**
 * Fetch the active language's due batch (`GET /review/due?language_id=…`).
 *
 * `languageId` may be `null` (no language selected yet); the query stays disabled until one exists.
 * The batch is a snapshot the screen walks through client-side — grading does not refetch mid-session
 * (so the queue doesn't reshuffle under the user); it refreshes on remount / when cards are saved.
 */
export function useDueQuery(languageId: number | null) {
  return useQuery({
    queryKey: dueKey(languageId ?? -1),
    queryFn: () =>
      unwrap(
        getApiClient().GET('/review/due', {
          params: { query: { language_id: languageId as number } },
        }),
      ),
    enabled: languageId !== null,
  });
}

/** Input to {@link useGradeCard}: the card and its FSRS rating (1..4). */
export interface GradeInput {
  cardId: number;
  rating: number;
}

/**
 * Grade a card (`POST /review/{card_id}/grade` with `{ rating }`).
 *
 * Deliberately does NOT invalidate the due query: the screen advances through the loaded snapshot
 * locally, so refetching here would reshuffle the batch mid-review. The queue refreshes naturally on
 * the next mount or when new cards are saved.
 */
export function useGradeCard() {
  return useMutation({
    mutationFn: (input: GradeInput): Promise<GradeResponse> =>
      unwrap(
        getApiClient().POST('/review/{card_id}/grade', {
          params: { path: { card_id: input.cardId } },
          body: { rating: input.rating },
        }),
      ),
  });
}

/** Parameters for an explanation request (a tapped word in a production card's sentence). */
export interface ExplainParams {
  languageId: number;
  /** The bare tapped word. */
  word: string;
  /** The target-language sentence (the production card's back). */
  sentence: string;
  /** Its English gloss (the production card's front). */
  translation: string;
}

/**
 * Query key for a tapped-word explanation — keyed by word + language (group 4.6.4).
 *
 * An explanation of a word in a language is stable, so this is all the identity the cache needs; the
 * backend likewise caches per bare word. Keying this way means tapping the same word twice never
 * re-fetches.
 */
export function explainKey(languageId: number, word: string) {
  return ['explain', languageId, word] as const;
}

/**
 * Fetch the explanation for a tapped word (`POST /explain`), keyed by word + language.
 *
 * Disabled until a word is selected (`params === null`). Explanations never go stale (a word's gloss
 * doesn't change), so the query is fetched once per word and then served from cache. When the card
 * already carries a pre-generated note for the word (`initialExplanation`), it is used as initial
 * data so the popover is instant and no request is made at all.
 */
export function useExplainWord(
  params: ExplainParams | null,
  initialExplanation?: string,
) {
  return useQuery({
    queryKey: explainKey(params?.languageId ?? -1, params?.word ?? ''),
    queryFn: () =>
      unwrap(
        getApiClient().POST('/explain', {
          body: {
            language_id: params!.languageId,
            word: params!.word,
            sentence: params!.sentence,
            translation: params!.translation,
          },
        }),
      ),
    enabled: params !== null,
    staleTime: Infinity,
    initialData:
      params !== null && initialExplanation !== undefined
        ? ({
            word: params.word,
            explanation: initialExplanation,
          } satisfies ExplainResponse)
        : undefined,
  });
}

/**
 * The pre-generated note for `word` carried on a card, if any.
 *
 * `card.word_explanations` is an untyped `{ [word]: unknown }` map (only production cards carry it,
 * keyed by bare word). Returns the note only when it is actually a string, so a malformed entry
 * degrades to "fetch it" rather than rendering a non-string.
 */
export function cardExplanation(
  explanations: Record<string, unknown> | null | undefined,
  word: string,
): string | undefined {
  const note = explanations?.[word];
  return typeof note === 'string' ? note : undefined;
}
