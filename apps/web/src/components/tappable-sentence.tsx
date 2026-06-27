/**
 * Tap-a-word sentence (groups 4.6.4 + 4.9.4) — renders a target-language sentence whose words can be
 * tapped for a short explanation in a popover, with full RTL + diacritics support.
 *
 * Used on production review cards: each whitespace token becomes a button; tapping one opens a
 * popover anchored to that word and fetches its explanation via `POST /explain` (keyed by word +
 * language, served from the card's pre-generated note when present). A single tap (mouse or touch —
 * a tap synthesises a click) selects the word; tapping it again, the close button, `Escape`, or
 * anywhere outside dismisses the popover.
 *
 * RTL + diacritics (4.9): direction + script font come from the language code, so an Arabic/Hebrew
 * sentence reads right-to-left in a harakat/nikkud-correct font and the popover anchors to the
 * correct edge. Word boundaries come from {@link segmentSentence} (exact on touch and click), and
 * the visible glyphs honour the vowel-marks toggle — but the word looked up is always the canonical
 * one WITH its marks ({@link SentenceSegment.bare}), so a stripped display still matches the cached
 * explanation key.
 */
import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';

import {
  cardExplanation,
  segmentSentence,
  useExplainWord,
  type ExplainParams,
} from '@/lib/review';
import {
  directionForCode,
  displayText,
  scriptFontClass,
} from '@/lib/language-text';
import type { LanguageOut } from '@/lib/languages';
import { cn } from '@/lib/utils';

export interface TappableSentenceProps {
  /** The target-language sentence (the production card's back). */
  text: string;
  /** Its English gloss (the production card's front), sent with the explain request. */
  translation: string;
  /** The active language (its id keys the explanation cache; its code drives direction + font). */
  language: Pick<LanguageOut, 'id' | 'code'>;
  /** The card's pre-generated word→note map, if any (instant popover, no request). */
  explanations: Record<string, unknown> | null;
  /** Whether to show vowel marks (false strips harakat / nikkud from the displayed glyphs). */
  showVowels: boolean;
}

/** The currently-tapped word: its bare form plus the segment index it was tapped at (the anchor). */
interface Selection {
  word: string;
  index: number;
}

export function TappableSentence({
  text,
  translation,
  language,
  explanations,
  showVowels,
}: TappableSentenceProps) {
  const [selection, setSelection] = useState<Selection | null>(null);
  const rootRef = useRef<HTMLParagraphElement>(null);
  const segments = segmentSentence(text);
  const dir = directionForCode(language.code);
  const fontClass = scriptFontClass(language.code);

  const explainParams: ExplainParams | null =
    selection === null
      ? null
      : {
          languageId: language.id,
          word: selection.word,
          sentence: text,
          translation,
        };
  const explain = useExplainWord(
    explainParams,
    selection === null
      ? undefined
      : cardExplanation(explanations, selection.word),
  );

  // Dismiss on Escape or a pointer-down outside the sentence (the close button / re-tap close from
  // their own handlers). Only wired while a word is selected.
  useEffect(() => {
    if (selection === null) {
      return;
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setSelection(null);
      }
    }
    function onPointerDown(event: PointerEvent) {
      if (
        rootRef.current !== null &&
        !rootRef.current.contains(event.target as Node)
      ) {
        setSelection(null);
      }
    }
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('pointerdown', onPointerDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('pointerdown', onPointerDown);
    };
  }, [selection]);

  function toggle(word: string, index: number) {
    setSelection((current) =>
      current !== null && current.index === index ? null : { word, index },
    );
  }

  return (
    <p
      ref={rootRef}
      dir={dir}
      className={cn('text-xl font-medium leading-relaxed', fontClass)}
    >
      {segments.map((segment, index) => {
        if (!segment.isWord) {
          return <span key={index}>{segment.raw}</span>;
        }
        const isOpen = selection !== null && selection.index === index;
        return (
          <span key={index} className="relative inline-block">
            <button
              type="button"
              // The looked-up word is the canonical bare form WITH marks; only the glyphs honour the
              // vowel-marks toggle.
              onClick={() => toggle(segment.bare, index)}
              aria-expanded={isOpen}
              aria-haspopup="dialog"
              className={cn(
                'rounded px-0.5 transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                isOpen && 'bg-accent text-accent-foreground',
              )}
            >
              {displayText(segment.raw, showVowels)}
            </button>
            {isOpen && (
              <WordPopover
                word={displayText(selection.word, showVowels)}
                explanation={explain.data?.explanation}
                isLoading={explain.isLoading}
                isError={explain.isError}
                dir={dir}
                fontClass={fontClass}
                onClose={() => setSelection(null)}
              />
            )}
          </span>
        );
      })}
    </p>
  );
}

interface WordPopoverProps {
  word: string;
  explanation: string | undefined;
  isLoading: boolean;
  isError: boolean;
  dir: 'ltr' | 'rtl';
  fontClass: string;
  onClose: () => void;
}

/** The floating explanation card anchored above a tapped word. */
function WordPopover({
  word,
  explanation,
  isLoading,
  isError,
  dir,
  fontClass,
  onClose,
}: WordPopoverProps) {
  return (
    <span
      role="dialog"
      aria-label={`Explanation of ${word}`}
      data-testid="word-popover"
      dir={dir}
      className={cn(
        'absolute bottom-full z-30 mb-2 block w-64 rounded-md border bg-popover p-3 text-left text-sm font-normal text-popover-foreground shadow-md',
        dir === 'rtl' ? 'right-0' : 'left-0',
      )}
    >
      <span className="flex items-start justify-between gap-2">
        <span className={cn('font-semibold', fontClass)}>{word}</span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close explanation"
          className="-mr-1 -mt-1 rounded p-1 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </span>
      <span className="mt-1 block text-muted-foreground" aria-live="polite">
        {isLoading && 'Explaining…'}
        {isError && "Couldn't load an explanation right now."}
        {explanation !== undefined && explanation}
      </span>
    </span>
  );
}
