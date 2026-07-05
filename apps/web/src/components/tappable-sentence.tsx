/**
 * Tap-a-word sentence (groups 4.6.4 + 4.9.4) — renders a target-language sentence whose words can be
 * tapped for a short explanation in a popover, with full RTL + diacritics support.
 *
 * Used on production review cards: each whitespace token becomes a button; tapping one opens a
 * popover anchored to that word and fetches its explanation via `POST /explain` (keyed by word +
 * language + card, since the backend explains a word *within its sentence*, served from the card's
 * pre-generated note when present). The popover is an announced `role="dialog"` with **managed
 * focus**: focus moves into it on open and is restored to the triggering word on `Escape` / close,
 * so a keyboard/SR user lands on the explanation instead of having to tab across the sentence to
 * reach it. A single tap (mouse or touch — a tap synthesises a click) selects the word; tapping it
 * again, the close button, `Escape`, or anywhere outside dismisses the popover.
 *
 * RTL + diacritics (4.9): direction + script font come from the language code, so an Arabic/Hebrew
 * sentence reads right-to-left in a harakat/nikkud-correct font and the popover anchors to the
 * correct edge. Word boundaries come from {@link segmentSentence} (exact on touch and click), and
 * the visible glyphs honour the vowel-marks toggle — but the word looked up is always the canonical
 * one WITH its marks ({@link SentenceSegment.bare}), so a stripped display still matches the cached
 * explanation key.
 */
import { useEffect, useId, useRef, useState } from 'react';
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
  /**
   * The card this sentence belongs to — scopes the explanation cache so the note stays matched to
   * this card's sentence (the backend explains a word *within a sentence*, so the same word can have
   * a different explanation on another card).
   */
  cardId: number;
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
  cardId,
  text,
  translation,
  language,
  explanations,
  showVowels,
}: TappableSentenceProps) {
  const [selection, setSelection] = useState<Selection | null>(null);
  const rootRef = useRef<HTMLParagraphElement>(null);
  // The word button that opened the current popover — focus is restored here on Escape / close so it
  // never strands on the removed dialog (WCAG 2.4.3).
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const popoverId = useId();
  const segments = segmentSentence(text);
  const dir = directionForCode(language.code);
  const fontClass = scriptFontClass(language.code);
  // Screen readers read the whole document as `lang="en"`; tag the target-language text so an
  // Arabic/Hebrew/Spanish sentence isn't sounded out with English phonetics (WCAG 3.1.2).
  const lang = language.code || undefined;

  const explainParams: ExplainParams | null =
    selection === null
      ? null
      : {
          languageId: language.id,
          cardId,
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
        // Return focus to the word that opened the dialog (the button stays mounted).
        triggerRef.current?.focus();
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
      lang={lang}
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
              onClick={(event) => {
                // Remember this button so focus can be restored to it when the dialog closes.
                triggerRef.current = event.currentTarget;
                toggle(segment.bare, index);
              }}
              aria-expanded={isOpen}
              aria-haspopup="dialog"
              aria-controls={isOpen ? popoverId : undefined}
              className={cn(
                'rounded-sm px-0.5 underline decoration-dotted decoration-muted-foreground/50 underline-offset-4 transition-colors duration-150 hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                isOpen && 'bg-accent text-accent-foreground',
              )}
            >
              {displayText(segment.raw, showVowels)}
            </button>
            {isOpen && (
              <WordPopover
                id={popoverId}
                word={displayText(selection.word, showVowels)}
                explanation={explain.data?.explanation}
                isLoading={explain.isLoading}
                isError={explain.isError}
                dir={dir}
                lang={lang}
                fontClass={fontClass}
                onClose={() => {
                  setSelection(null);
                  // Restore focus to the word that opened the dialog.
                  triggerRef.current?.focus();
                }}
              />
            )}
          </span>
        );
      })}
    </p>
  );
}

interface WordPopoverProps {
  /** The id the trigger word references via `aria-controls`. */
  id: string;
  word: string;
  explanation: string | undefined;
  isLoading: boolean;
  isError: boolean;
  dir: 'ltr' | 'rtl';
  /** The target-language code, so the headword is read in the right language (WCAG 3.1.2). */
  lang: string | undefined;
  fontClass: string;
  onClose: () => void;
}

/**
 * The floating explanation card anchored above a tapped word.
 *
 * An announced `role="dialog"` with managed focus: it grabs focus on mount (the container is
 * `tabIndex={-1}` and named by `aria-label`), so a keyboard/SR user lands on the explanation the
 * dialog announces instead of having to hunt for it; the trigger restores focus to itself on close.
 */
function WordPopover({
  id,
  word,
  explanation,
  isLoading,
  isError,
  dir,
  lang,
  fontClass,
  onClose,
}: WordPopoverProps) {
  const ref = useRef<HTMLSpanElement>(null);
  // Move focus into the dialog on open (it is announced, so focus must land inside it).
  useEffect(() => {
    ref.current?.focus();
  }, []);
  return (
    <span
      ref={ref}
      id={id}
      role="dialog"
      aria-label={`Explanation of ${word}`}
      tabIndex={-1}
      data-testid="word-popover"
      dir={dir}
      className={cn(
        'absolute bottom-full z-30 mb-2 block max-w-xs rounded-lg border bg-popover p-4 text-left font-normal text-popover-foreground shadow-raised focus-visible:outline-none',
        dir === 'rtl' ? 'right-0' : 'left-0',
      )}
    >
      <span className="flex items-start justify-between gap-2">
        <span lang={lang} className={cn('text-body font-semibold', fontClass)}>
          {word}
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close explanation"
          className="-mr-1 -mt-1 rounded p-1 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </span>
      <span
        className="mt-1 block text-subhead text-muted-foreground"
        aria-live="polite"
      >
        {isLoading && 'Explaining…'}
        {isError && "Couldn't load an explanation right now."}
        {explanation !== undefined && explanation}
      </span>
    </span>
  );
}
