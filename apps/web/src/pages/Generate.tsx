/**
 * Generate screen (group 4.5) — the React port of the legacy Streamlit "generate" page.
 *
 * Flow: paste vocabulary words for the ACTIVE language -> `POST /generate` builds an example
 * sentence (recognition + production card pair) for each -> review them grouped back into
 * sentences -> select which to keep (all by default) -> `POST /cards/save` persists the chosen
 * ones. Generation is slow and quota-bounded, so the in-progress state and the friendly 429
 * daily-limit state (the shared {@link DailyLimitPanel}) are first-class here; other cost-guard
 * states (rate-limited / server-busy / verify-email) render friendly inline messages too, never a
 * raw error.
 */
import { useMemo, useState } from 'react';
import { m } from 'framer-motion';
import type { Variants } from 'framer-motion';
import { CheckCircle2, Loader2, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';

import { useActiveLanguage } from '@/components/active-language-context';
import { EmptyState } from '@/components/empty-state';
import { ErrorState } from '@/components/error-state';
import { LanguageText } from '@/components/language-text';
import { LlmErrorState } from '@/components/llm-error-state';
import { LoadingState } from '@/components/loading-state';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { toast } from '@/components/ui/use-toast';
import { useVowelMarks } from '@/components/vowel-marks-context';
import { VowelMarksToggle } from '@/components/vowel-marks-toggle';
import { apiErrorMessage } from '@/lib/api-client';
import { directionForCode } from '@/lib/language-text';
import { fallbackLanguage, type LanguageOut } from '@/lib/languages';
import {
  cardsForSentences,
  groupSentences,
  parseWords,
  useGenerate,
  useSaveCards,
  WORDS_PER_REQUEST_CAP,
  type GeneratedCard,
  type GeneratedSentence,
} from '@/lib/generate';
import { takeHandedOffWords } from '@/lib/generate-handoff';
import { cn } from '@/lib/utils';

export default function Generate() {
  const { activeLanguageId, activeLanguage, isLoading, isError, refetch } =
    useActiveLanguage();
  const { showVowels } = useVowelMarks();

  return (
    <section
      dir={directionForCode(activeLanguage?.code)}
      data-testid="generate-content"
      className="mx-auto max-w-2xl space-y-8"
    >
      <div className="space-y-1">
        <h1 className="text-large-title">Generate</h1>
        <p className="text-subhead text-muted-foreground">
          Paste vocabulary words and generate natural example sentences
          {activeLanguage !== null ? ` in ${activeLanguage.name}` : ''}.
        </p>
      </div>

      <VowelMarksToggle />

      {isLoading ? (
        <LoadingState label="Loading your languages…" />
      ) : isError ? (
        <ErrorState
          title="Couldn't load your languages"
          description="Something went wrong loading your languages."
          onRetry={refetch}
        />
      ) : activeLanguageId === null ? (
        <EmptyState
          title="Add a language first"
          description="You need a language before you can generate sentences."
        >
          <Button asChild>
            <Link to="/languages">Add a language</Link>
          </Button>
        </EmptyState>
      ) : (
        // Re-mount the workspace per language so its draft/results never leak across a switch.
        <GenerateWorkspace
          key={activeLanguageId}
          language={activeLanguage ?? fallbackLanguage(activeLanguageId)}
          showVowels={showVowels}
        />
      )}
    </section>
  );
}

/** The generate -> review -> save workflow for a known (non-null) active language. */
function GenerateWorkspace({
  language,
  showVowels,
}: {
  language: LanguageOut;
  showVowels: boolean;
}) {
  const languageId = language.id;
  // Seed the word input from a Discover → Generate handoff (group 4.7.2), consumed once on mount so a
  // later language switch or revisit starts blank; normal visits get an empty form.
  const [rawWords, setRawWords] = useState(() => {
    const handed = takeHandedOffWords();
    return handed !== null ? handed.join('\n') : '';
  });
  const [sentences, setSentences] = useState<GeneratedSentence[] | null>(null);
  const [savedCount, setSavedCount] = useState<number | null>(null);

  const generate = useGenerate();
  const save = useSaveCards();

  const words = useMemo(() => parseWords(rawWords), [rawWords]);
  const overCap = words.length > WORDS_PER_REQUEST_CAP;
  const canGenerate = words.length > 0 && !overCap && !generate.isPending;

  function handleGenerate(event: React.FormEvent) {
    event.preventDefault();
    if (words.length === 0 || overCap) {
      return;
    }
    // Re-running clears any prior saved confirmation / stale save error.
    setSavedCount(null);
    save.reset();
    generate.mutate(
      { languageId, words },
      {
        onSuccess: (cards) => {
          setSentences(groupSentences(cards));
        },
      },
    );
  }

  function handleSave(cards: GeneratedCard[]) {
    save.mutate(
      { languageId, cards },
      {
        onSuccess: (saved) => {
          setSavedCount(saved.length);
          setSentences(null);
          toast({
            title: 'Cards saved',
            description: `${saved.length} card${
              saved.length === 1 ? '' : 's'
            } added to your deck.`,
          });
        },
        onError: (error) => {
          toast({
            variant: 'destructive',
            title: 'Could not save cards',
            description: apiErrorMessage(error, 'Please try again.'),
          });
        },
      },
    );
  }

  /** Return to the word form. `clearWords` starts fresh (after a save); otherwise keeps the words. */
  function startOver(clearWords: boolean) {
    generate.reset();
    save.reset();
    setSentences(null);
    setSavedCount(null);
    if (clearWords) {
      setRawWords('');
    }
  }

  if (savedCount !== null) {
    return (
      <SavedConfirmation
        count={savedCount}
        onGenerateMore={() => startOver(true)}
      />
    );
  }

  if (sentences !== null) {
    return (
      <ResultsPanel
        sentences={sentences}
        language={language}
        showVowels={showVowels}
        onSave={handleSave}
        onStartOver={() => startOver(false)}
        isSaving={save.isPending}
      />
    );
  }

  return (
    <WordForm
      rawWords={rawWords}
      onRawWordsChange={setRawWords}
      words={words}
      language={language}
      showVowels={showVowels}
      overCap={overCap}
      canGenerate={canGenerate}
      isGenerating={generate.isPending}
      onSubmit={handleGenerate}
      error={generate.isPending ? null : (generate.error ?? null)}
    />
  );
}

interface WordFormProps {
  rawWords: string;
  onRawWordsChange: (value: string) => void;
  words: string[];
  language: LanguageOut;
  showVowels: boolean;
  overCap: boolean;
  canGenerate: boolean;
  isGenerating: boolean;
  onSubmit: (event: React.FormEvent) => void;
  error: unknown;
}

function WordForm({
  rawWords,
  onRawWordsChange,
  words,
  language,
  showVowels,
  overCap,
  canGenerate,
  isGenerating,
  onSubmit,
  error,
}: WordFormProps) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Your words</CardTitle>
          <CardDescription>
            One word or phrase per line (or comma-separated). Up to{' '}
            {WORDS_PER_REQUEST_CAP} at a time.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <div className="space-y-1.5">
              <label htmlFor="generate-words" className="text-body font-medium">
                Words
              </label>
              <Textarea
                id="generate-words"
                dir={directionForCode(language.code)}
                value={rawWords}
                onChange={(event) => onRawWordsChange(event.target.value)}
                disabled={isGenerating}
                rows={5}
                className="min-h-[160px]"
                placeholder={'casa\nperro\nbuenos días'}
                aria-describedby="generate-words-count"
              />
              <p
                id="generate-words-count"
                className={cn(
                  'text-right text-footnote tabular-nums',
                  // Warm-orange nudge once you hit the cap (30/30 and beyond).
                  words.length >= WORDS_PER_REQUEST_CAP
                    ? 'font-medium text-hig-orange-deep'
                    : 'text-muted-foreground',
                )}
              >
                {words.length} / {WORDS_PER_REQUEST_CAP} words
              </p>
            </div>

            {words.length > 0 && (
              <ul
                className="flex flex-wrap gap-1.5"
                aria-label="Parsed entries"
              >
                {words.map((word, index) => (
                  <li
                    key={`${word}-${index}`}
                    className="rounded-full bg-secondary px-2.5 py-0.5 text-footnote text-muted-foreground"
                  >
                    <LanguageText
                      as="span"
                      text={word}
                      language={language}
                      showVowels={showVowels}
                    />
                  </li>
                ))}
              </ul>
            )}

            {overCap && (
              <p role="alert" className="text-subhead text-destructive">
                Too many words. Remove {words.length - WORDS_PER_REQUEST_CAP} to
                generate up to {WORDS_PER_REQUEST_CAP} at a time.
              </p>
            )}

            <div className="flex items-center gap-3">
              {/* The label stays "Generate" throughout — the spinner swaps in beside it while
                  in flight, so the button's accessible name never changes (pinned contract).
                  The live-region line below carries the human "generating…" status. */}
              <Button type="submit" disabled={!canGenerate}>
                {isGenerating ? (
                  <Loader2
                    className="h-4 w-4 animate-spin"
                    aria-hidden="true"
                  />
                ) : (
                  <Sparkles className="h-4 w-4" aria-hidden="true" />
                )}
                Generate
              </Button>
              {isGenerating && (
                <span
                  className="text-subhead text-muted-foreground"
                  aria-live="polite"
                >
                  Generating sentences… this can take a few seconds.
                </span>
              )}
            </div>
          </form>
        </CardContent>
      </Card>

      {error !== null && (
        <LlmErrorState
          error={error}
          transientHint="Your words are kept — press Generate to try again."
        />
      )}
    </div>
  );
}

interface ResultsPanelProps {
  sentences: GeneratedSentence[];
  language: LanguageOut;
  showVowels: boolean;
  onSave: (cards: GeneratedCard[]) => void;
  onStartOver: () => void;
  isSaving: boolean;
}

function ResultsPanel({
  sentences,
  language,
  showVowels,
  onSave,
  onStartOver,
  isSaving,
}: ResultsPanelProps) {
  // Default to all selected (the common case is "keep them all"). Owned here so it resets whenever
  // a fresh result set mounts this panel.
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(
    () => new Set(sentences.map((sentence) => sentence.key)),
  );

  function toggle(key: string) {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  const selected = sentences.filter((sentence) =>
    selectedKeys.has(sentence.key),
  );
  const allSelected = selected.length === sentences.length;

  function toggleAll() {
    setSelectedKeys(
      allSelected ? new Set() : new Set(sentences.map((s) => s.key)),
    );
  }

  if (sentences.length === 0) {
    return (
      <EmptyState
        title="No sentences generated"
        description="Nothing came back for those words. Try different ones."
      >
        <Button variant="outline" onClick={onStartOver}>
          Back to words
        </Button>
      </EmptyState>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h2 className="text-title2">Review &amp; save</h2>
        <p className="text-subhead text-muted-foreground">
          Pick the sentences to add to your deck. Each becomes two flashcards
          (reading + writing).
        </p>
      </div>

      <div className="flex items-center justify-between">
        <label className="flex items-center gap-2 text-subhead font-medium">
          <input
            type="checkbox"
            checked={allSelected}
            onChange={toggleAll}
            className="h-4 w-4 rounded border-input"
            aria-label="Select all sentences"
          />
          Select all
        </label>
        <span className="text-subhead tabular-nums text-muted-foreground">
          {selected.length} of {sentences.length} selected
        </span>
      </div>

      {/* Grouped list (iOS inset cells). Rows stagger in on mount; reduced-motion-safe. */}
      <m.ul
        className="divide-y overflow-hidden rounded-lg border bg-card shadow-card"
        initial="hidden"
        animate="show"
        variants={RESULTS_LIST_VARIANTS}
      >
        {sentences.map((sentence) => {
          const checked = selectedKeys.has(sentence.key);
          return (
            <m.li
              key={sentence.key}
              variants={RESULTS_ROW_VARIANTS}
              className={cn(
                'flex gap-3 px-5 py-4 transition-colors duration-150',
                checked && 'bg-primary/[0.04]',
              )}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => toggle(sentence.key)}
                className="mt-1 h-4 w-4 shrink-0 rounded border-input"
                aria-label={`Save this card — ${sentence.translation}`}
              />
              <div className="min-w-0 space-y-1">
                <LanguageText
                  className="text-[17px] font-medium leading-snug"
                  text={sentence.sentence}
                  language={language}
                  showVowels={showVowels}
                />
                <p className="text-subhead text-muted-foreground">
                  {sentence.translation}
                </p>
                {sentence.usedWords.length > 0 && (
                  <ul className="flex flex-wrap gap-1.5 pt-1">
                    {sentence.usedWords.map((word, index) => (
                      <li
                        key={`${word}-${index}`}
                        className="rounded-full bg-secondary px-2 py-0.5 text-footnote text-muted-foreground"
                      >
                        <LanguageText
                          as="span"
                          text={word}
                          language={language}
                          showVowels={showVowels}
                        />
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </m.li>
          );
        })}
      </m.ul>

      {/* On mobile this is a sticky action bar pinned just above the tab bar (49px + safe area
          + 12px), matching PR2's toast offset so it never covers content or lands under the bar;
          on `sm` and up it is a normal inline row. */}
      <div className="sticky bottom-[calc(49px+env(safe-area-inset-bottom)+12px)] z-10 -mx-4 flex items-center gap-3 border-t border-border/60 bg-background/85 px-4 py-3 backdrop-blur-lg sm:static sm:mx-0 sm:border-0 sm:bg-transparent sm:px-0 sm:py-0 sm:backdrop-blur-none">
        <Button
          onClick={() => onSave(cardsForSentences(selected))}
          disabled={selected.length === 0 || isSaving}
        >
          {isSaving ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Saving…
            </>
          ) : (
            `Save ${selected.length} ${
              selected.length === 1 ? 'sentence' : 'sentences'
            }`
          )}
        </Button>
        <Button variant="ghost" onClick={onStartOver} disabled={isSaving}>
          Start over
        </Button>
      </div>
    </div>
  );
}

// Results grouped-list rows fade/slide up in sequence (~40ms apart) on mount. Under reduced
// motion (and jsdom) they settle at their final state immediately.
const RESULTS_LIST_VARIANTS: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.04 } },
};
const RESULTS_ROW_VARIANTS: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.2, ease: [0.32, 0.72, 0, 1] },
  },
};

interface SavedConfirmationProps {
  count: number;
  onGenerateMore: () => void;
}

function SavedConfirmation({ count, onGenerateMore }: SavedConfirmationProps) {
  return (
    <Card className="border-hig-green/25">
      <CardHeader>
        <div className="flex items-center gap-2">
          <CheckCircle2
            className="h-5 w-5 shrink-0 text-hig-green-deep"
            aria-hidden="true"
          />
          <CardTitle>
            Saved {count} {count === 1 ? 'card' : 'cards'}
          </CardTitle>
        </div>
        <CardDescription>
          They are in your deck and due for review now.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex items-center gap-3">
        <Button onClick={onGenerateMore}>Generate more</Button>
        <Button variant="outline" asChild>
          <Link to="/review">Review now</Link>
        </Button>
      </CardContent>
    </Card>
  );
}
