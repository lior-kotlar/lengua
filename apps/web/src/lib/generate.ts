/**
 * Generate / save data layer — TanStack Query mutations over the typed API client, plus the pure
 * helpers the Generate screen (group 4.5) builds on.
 *
 * The flow: paste words -> `POST /generate` returns the recognition + production card pair for each
 * example sentence (a flat list) -> the user reviews them grouped back into sentences and saves the
 * selected ones via `POST /cards/save`. Everything goes through `getApiClient()` (auth + 401-retry)
 * and `unwrap()` (typed data / typed {@link import('@/lib/api-client').ApiError}); Supabase is
 * auth-only.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { schemaLimits, type components } from 'api-types';

import { trackGenerate } from '@/lib/analytics-events';
import { getApiClient, unwrap } from '@/lib/api-client';

/** One built (unsaved) flashcard direction returned by `POST /generate`. */
export type GeneratedCard = components['schemas']['GeneratedCardModel'];

/** A persisted flashcard row returned by `POST /cards/save`. */
export type CardOut = components['schemas']['CardOut'];

/**
 * Max words accepted by `POST /generate` in one request, read from the OpenAPI contract
 * (`GenerateRequest.words.maxItems`) rather than hard-coded — so the client cap always matches the
 * server's. The form warns (and blocks) past this before the server would 422.
 */
export const WORDS_PER_REQUEST_CAP = schemaLimits.generateWordsMaxItems;

/**
 * The `direction` value of a production card (English -> target sentence). Mirrors
 * `lengua_core.cards.PRODUCTION`; used only to orient a card's front/back back into a sentence +
 * translation for display (anything that isn't production is treated as the recognition direction).
 */
const PRODUCTION_DIRECTION = 'production';

/**
 * Parse the word-input textarea into a clean word/phrase list.
 *
 * Entries are separated by newlines or commas (NOT spaces, so multi-word phrases like "buenos
 * dias" stay intact); each is trimmed and blanks are dropped. Order is preserved.
 */
export function parseWords(raw: string): string[] {
  return raw
    .split(/[\n,]+/)
    .map((word) => word.trim())
    .filter((word) => word !== '');
}

/** One example sentence grouped from its recognition + production card pair, for display + save. */
export interface GeneratedSentence {
  /** Stable key for React lists + selection: the target-language sentence text. */
  key: string;
  /** The example sentence in the target language. */
  sentence: string;
  /** Its English translation. */
  translation: string;
  /** The vocabulary words the sentence was built from. */
  usedWords: string[];
  /** The underlying generated cards (both directions) to persist when this sentence is selected. */
  cards: GeneratedCard[];
}

/**
 * Group the flat `POST /generate` card list back into example sentences.
 *
 * The backend returns two cards per sentence — a recognition card (front = target sentence, back =
 * English) and a production card (front = English, back = target sentence). We re-pair them by the
 * target-sentence text so the UI shows one selectable sentence (sentence + translation + used
 * words) while still saving BOTH directions when it is selected. Robust to ordering and to either
 * direction arriving first.
 */
export function groupSentences(cards: GeneratedCard[]): GeneratedSentence[] {
  const sentences: GeneratedSentence[] = [];
  const byKey = new Map<string, GeneratedSentence>();

  for (const card of cards) {
    const isProduction = card.direction === PRODUCTION_DIRECTION;
    const sentence = isProduction ? card.back : card.front;
    const translation = isProduction ? card.front : card.back;

    let group = byKey.get(sentence);
    if (group === undefined) {
      group = {
        key: sentence,
        sentence,
        translation,
        usedWords: card.used_words,
        cards: [],
      };
      byKey.set(sentence, group);
      sentences.push(group);
    }
    group.cards.push(card);
  }

  return sentences;
}

/** Flatten the selected sentences back into the card list `POST /cards/save` expects. */
export function cardsForSentences(
  sentences: GeneratedSentence[],
): GeneratedCard[] {
  return sentences.flatMap((sentence) => sentence.cards);
}

/** Input to {@link useGenerate}. */
export interface GenerateInput {
  languageId: number;
  words: string[];
}

/** `POST /generate`: build recognition + production previews for `words` (nothing persisted yet). */
export function useGenerate() {
  return useMutation({
    mutationFn: (input: GenerateInput): Promise<GeneratedCard[]> =>
      unwrap(
        getApiClient().POST('/generate', {
          body: { language_id: input.languageId, words: input.words },
        }),
      ),
    // Activation-funnel event (5.9.2): consent-gated, only the word count (no words/PII).
    onSuccess: (_cards, input) => trackGenerate(input.words.length),
  });
}

/** Input to {@link useSaveCards}. */
export interface SaveCardsInput {
  languageId: number;
  cards: GeneratedCard[];
}

/**
 * `POST /cards/save`: persist the chosen generated previews into the deck (saved, due now).
 *
 * On success the Review cache is invalidated — saved cards are immediately due, so the active
 * language's review queue changed. We invalidate the whole `['review', ...]` key space so it stays
 * correct regardless of how the Review screen (group 4.6) sub-keys its due query.
 */
export function useSaveCards() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: SaveCardsInput): Promise<CardOut[]> =>
      unwrap(
        getApiClient().POST('/cards/save', {
          body: { language_id: input.languageId, cards: input.cards },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['review'] });
    },
  });
}
