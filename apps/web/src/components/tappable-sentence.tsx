/**
 * Tap-a-word sentence (group 4.6.4) — renders a target-language sentence whose words can be tapped
 * for a short explanation in a popover.
 *
 * Used on production review cards: each whitespace token becomes a button; tapping one opens a
 * popover anchored to that word and fetches its explanation via `POST /explain` (keyed by word +
 * language, served from the card's pre-generated note when present). A single tap (mouse or touch —
 * a tap synthesises a click) selects the word; tapping it again, the close button, `Escape`, or
 * anywhere outside dismisses the popover. Word boundaries come from {@link segmentSentence}, so they
 * are exact on both touch and click. (RTL-aware refinements land in group 4.9.)
 */
import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';

import {
  cardExplanation,
  segmentSentence,
  useExplainWord,
  type ExplainParams,
} from '@/lib/review';
import { cn } from '@/lib/utils';

export interface TappableSentenceProps {
  /** The target-language sentence (the production card's back). */
  text: string;
  /** Its English gloss (the production card's front), sent with the explain request. */
  translation: string;
  /** The active language id (part of the explanation cache key). */
  languageId: number;
  /** The card's pre-generated word→note map, if any (instant popover, no request). */
  explanations: Record<string, unknown> | null;
  /** Text direction for the sentence region (group 4.9 sets RTL; defaults to LTR). */
  dir?: 'ltr' | 'rtl';
}

/** The currently-tapped word: its bare form plus the segment index it was tapped at (the anchor). */
interface Selection {
  word: string;
  index: number;
}

export function TappableSentence({
  text,
  translation,
  languageId,
  explanations,
  dir = 'ltr',
}: TappableSentenceProps) {
  const [selection, setSelection] = useState<Selection | null>(null);
  const rootRef = useRef<HTMLParagraphElement>(null);
  const segments = segmentSentence(text);

  const explainParams: ExplainParams | null =
    selection === null
      ? null
      : { languageId, word: selection.word, sentence: text, translation };
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
    <p ref={rootRef} dir={dir} className="text-xl font-medium leading-relaxed">
      {segments.map((segment, index) => {
        if (!segment.isWord) {
          return <span key={index}>{segment.raw}</span>;
        }
        const isOpen = selection !== null && selection.index === index;
        return (
          <span key={index} className="relative inline-block">
            <button
              type="button"
              onClick={() => toggle(segment.bare, index)}
              aria-expanded={isOpen}
              aria-haspopup="dialog"
              className={cn(
                'rounded px-0.5 transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                isOpen && 'bg-accent text-accent-foreground',
              )}
            >
              {segment.raw}
            </button>
            {isOpen && (
              <WordPopover
                word={selection.word}
                explanation={explain.data?.explanation}
                isLoading={explain.isLoading}
                isError={explain.isError}
                dir={dir}
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
  onClose: () => void;
}

/** The floating explanation card anchored above a tapped word. */
function WordPopover({
  word,
  explanation,
  isLoading,
  isError,
  dir,
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
        <span className="font-semibold">{word}</span>
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
