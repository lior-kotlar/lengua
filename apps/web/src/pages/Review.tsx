/**
 * Review screen (group 4.6) — the React port of the legacy Streamlit review page.
 *
 * Flow: load the active language's due batch (`GET /review/due`, split into new vs. due), walk it
 * one card at a time — show the prompt (front), reveal the answer (back; the production card's
 * target sentence is tap-a-word enabled), then rate Again/Hard/Good/Easy in the LOCKED
 * red/orange/blue/green colours, which `POST`s the FSRS grade and advances. Keyboard shortcuts make
 * desktop review fast: space/enter reveals, 1–4 rate. When the batch is empty (or fully reviewed)
 * a clean "all caught up" state shows instead.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCircle2, RotateCcw } from 'lucide-react';
import { Link } from 'react-router-dom';

import { useActiveLanguage } from '@/components/active-language-context';
import { EmptyState } from '@/components/empty-state';
import { ErrorState } from '@/components/error-state';
import { LanguageText } from '@/components/language-text';
import { LoadingState } from '@/components/loading-state';
import { TappableSentence } from '@/components/tappable-sentence';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { toast } from '@/components/ui/use-toast';
import { useVowelMarks } from '@/components/vowel-marks-context';
import { VowelMarksToggle } from '@/components/vowel-marks-toggle';
import { apiErrorMessage } from '@/lib/api-client';
import { directionForCode } from '@/lib/language-text';
import { fallbackLanguage, type LanguageOut } from '@/lib/languages';
import {
  isProductionCard,
  RATINGS,
  ratingButtonClass,
  useDueQuery,
  useGradeCard,
  type CardOut,
} from '@/lib/review';
import { cn } from '@/lib/utils';

export default function Review() {
  const { activeLanguageId, activeLanguage, isLoading, isError, refetch } =
    useActiveLanguage();
  const { showVowels } = useVowelMarks();

  return (
    <section
      dir={directionForCode(activeLanguage?.code)}
      data-testid="review-content"
      className="mx-auto max-w-2xl space-y-6"
    >
      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Review</h1>
        <p className="text-sm text-muted-foreground">
          Review your due flashcards
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
          description="You need a language with some saved cards before you can review."
        >
          <Button asChild>
            <Link to="/languages">Add a language</Link>
          </Button>
        </EmptyState>
      ) : (
        // Re-mount the session per language so the walk position never leaks across a switch.
        <ReviewSession
          key={activeLanguageId}
          language={activeLanguage ?? fallbackLanguage(activeLanguageId)}
          showVowels={showVowels}
        />
      )}
    </section>
  );
}

interface ReviewSessionProps {
  language: LanguageOut;
  showVowels: boolean;
}

/** Load + walk the due batch for a known (non-null) active language. */
function ReviewSession({ language, showVowels }: ReviewSessionProps) {
  const languageId = language.id;
  const languageName = language.name;
  const due = useDueQuery(languageId);
  const grade = useGradeCard();
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);

  // Due cards first, then new — a stable snapshot the session walks (grading doesn't refetch).
  // Due-before-new matches the scheduler/legacy order, so quitting mid-session never buries the
  // reviews that are actually due behind a stack of brand-new cards.
  const batch = useMemo<CardOut[]>(
    () => (due.data !== undefined ? [...due.data.due, ...due.data.new] : []),
    [due.data],
  );
  const current = index < batch.length ? batch[index] : null;

  const reveal = useCallback(() => setRevealed(true), []);
  const advance = useCallback(() => {
    setRevealed(false);
    setIndex((value) => value + 1);
  }, []);

  const submitGrade = useCallback(
    (rating: number) => {
      if (current === null || grade.isPending) {
        return;
      }
      grade.mutate(
        { cardId: current.id, rating },
        {
          onSuccess: advance,
          onError: (error) => {
            toast({
              variant: 'destructive',
              title: 'Could not save your answer',
              description: apiErrorMessage(error, 'Please try again.'),
            });
          },
        },
      );
    },
    [current, grade, advance],
  );

  // Keyboard shortcuts (4.6.5): space/enter to reveal, 1–4 to rate. Wired only while a card is up.
  useEffect(() => {
    if (current === null) {
      return;
    }
    function onKeyDown(event: KeyboardEvent) {
      if (
        event.defaultPrevented ||
        event.metaKey ||
        event.ctrlKey ||
        event.altKey
      ) {
        return;
      }
      // Don't hijack typing in a form control (e.g. the header language picker or a future input).
      if (
        event.target instanceof HTMLElement &&
        event.target.closest(
          'input, textarea, select, [contenteditable="true"]',
        )
      ) {
        return;
      }
      if (!revealed) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          reveal();
        }
        return;
      }
      if (event.key >= '1' && event.key <= '4') {
        event.preventDefault();
        submitGrade(Number(event.key));
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [current, revealed, reveal, submitGrade]);

  function restart() {
    setIndex(0);
    setRevealed(false);
    void due.refetch();
  }

  if (due.isPending) {
    return <LoadingState label="Loading your due cards…" />;
  }

  if (due.isError) {
    return (
      <ErrorState
        title="Couldn't load your cards"
        description="Something went wrong fetching your due batch."
        onRetry={() => void due.refetch()}
      />
    );
  }

  if (batch.length === 0) {
    return <AllCaughtUp languageName={languageName} />;
  }

  if (current === null) {
    return <SessionComplete reviewed={batch.length} onReviewMore={restart} />;
  }

  return (
    <div className="space-y-4">
      <ReviewProgress
        newCount={due.data.new.length}
        dueCount={due.data.due.length}
        reviewed={index}
        total={batch.length}
      />
      <ReviewCard
        // Fresh card component (and tap-a-word state) per card.
        key={current.id}
        card={current}
        language={language}
        revealed={revealed}
        grading={grade.isPending}
        showVowels={showVowels}
        onReveal={reveal}
        onGrade={submitGrade}
      />
    </div>
  );
}

interface ReviewProgressProps {
  newCount: number;
  dueCount: number;
  reviewed: number;
  total: number;
}

/** The new/due counts header + a thin progress bar for the current session. */
function ReviewProgress({
  newCount,
  dueCount,
  reviewed,
  total,
}: ReviewProgressProps) {
  // `total` is always ≥ 1 here (the empty batch renders the all-caught-up state instead).
  const percent = Math.round((reviewed / total) * 100);
  return (
    <div className="space-y-1.5">
      <div
        className="flex items-center justify-between text-sm"
        data-testid="review-counts"
      >
        <p className="font-medium">
          <span className="text-foreground">{newCount} new</span>
          <span className="text-muted-foreground"> · </span>
          <span className="text-foreground">{dueCount} due</span>
        </p>
        <p className="text-muted-foreground">
          Card {Math.min(reviewed + 1, total)} of {total}
        </p>
      </div>
      <div
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Review progress"
        className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
      >
        <div
          className="h-full rounded-full bg-primary transition-[width]"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

interface ReviewCardProps {
  card: CardOut;
  language: LanguageOut;
  revealed: boolean;
  grading: boolean;
  showVowels: boolean;
  onReveal: () => void;
  onGrade: (rating: number) => void;
}

/** One review card: prompt (front), reveal control, then the answer + rating buttons. */
function ReviewCard({
  card,
  language,
  revealed,
  grading,
  showVowels,
  onReveal,
  onGrade,
}: ReviewCardProps) {
  const production = isProductionCard(card);
  const languageName = language.name;
  const promptLabel = production
    ? `Build the sentence${languageName !== '' ? ` in ${languageName}` : ''}`
    : 'Read and understand';
  const revealLabel = production ? 'Show answer' : 'Show translation';

  return (
    <Card>
      <CardHeader>
        <CardDescription>{promptLabel}</CardDescription>
        <CardTitle className="text-xl font-medium leading-relaxed">
          {/* The prompt is target text for recognition cards (read it) and English for production
              cards (build it) — only the former gets direction/font/diacritics treatment. */}
          {production ? (
            card.front
          ) : (
            <LanguageText
              as="span"
              text={card.front}
              language={language}
              showVowels={showVowels}
            />
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {!revealed ? (
          <div className="space-y-2">
            <Button onClick={onReveal}>{revealLabel}</Button>
            <p className="text-xs text-muted-foreground">
              or press <kbd className="rounded border px-1">space</kbd>
            </p>
          </div>
        ) : (
          <>
            <div className="border-t pt-4" data-testid="card-answer">
              {production ? (
                <TappableSentence
                  text={card.back}
                  translation={card.front}
                  language={language}
                  explanations={card.word_explanations}
                  showVowels={showVowels}
                />
              ) : (
                // A recognition card's answer is the ENGLISH translation, so render it as plain
                // text — exactly like a production card's English front (`card.front`) above. Only
                // target-language text gets LanguageText's direction/script-font/diacritics; passing
                // English through it forced an RTL deck's answer into the script font + dir="rtl",
                // which hid it. The recognition PROMPT (target text) keeps its LanguageText.
                <p className="text-xl font-medium leading-relaxed">
                  {card.back}
                </p>
              )}
              {production && (
                <p className="mt-1 text-xs text-muted-foreground">
                  Tap any word for a quick explanation.
                </p>
              )}
            </div>
            <RatingButtons onGrade={onGrade} disabled={grading} />
          </>
        )}
      </CardContent>
    </Card>
  );
}

interface RatingButtonsProps {
  onGrade: (rating: number) => void;
  disabled: boolean;
}

/** The four FSRS rating buttons in their LOCKED colours, with their keyboard digit. */
function RatingButtons({ onGrade, disabled }: RatingButtonsProps) {
  return (
    <div className="space-y-2">
      <div
        role="group"
        aria-label="Rate this card"
        className="grid grid-cols-2 gap-2 sm:grid-cols-4"
      >
        {RATINGS.map((rating) => (
          <button
            key={rating.value}
            type="button"
            onClick={() => onGrade(rating.value)}
            disabled={disabled}
            data-rating={rating.value}
            className={cn(
              'flex items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm font-semibold text-white transition-[filter,background-color] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50',
              ratingButtonClass(rating.color),
            )}
          >
            {rating.label}
            <kbd className="rounded bg-white/20 px-1 text-xs font-normal">
              {rating.value}
            </kbd>
          </button>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        Tip: press <kbd className="rounded border px-1">1</kbd>–
        <kbd className="rounded border px-1">4</kbd> to rate.
      </p>
    </div>
  );
}

/** Empty state: nothing is due for this language right now. */
function AllCaughtUp({ languageName }: { languageName: string }) {
  return (
    <EmptyState
      tone="success"
      icon={CheckCircle2}
      title="You're all caught up"
      description={`No cards are due${
        languageName !== '' ? ` in ${languageName}` : ''
      } right now. Generate some sentences to build your deck.`}
    >
      <Button asChild>
        <Link to="/generate">Generate sentences</Link>
      </Button>
    </EmptyState>
  );
}

interface SessionCompleteProps {
  reviewed: number;
  onReviewMore: () => void;
}

/** Reached the end of the loaded batch — offer to re-check for more or generate. */
function SessionComplete({ reviewed, onReviewMore }: SessionCompleteProps) {
  return (
    <Card className="border-green-500/50">
      <CardHeader>
        <div className="flex items-center gap-2">
          <CheckCircle2
            className="h-5 w-5 shrink-0 text-green-500"
            aria-hidden="true"
          />
          <CardTitle className="text-lg">Done for today</CardTitle>
        </div>
        <CardDescription>
          You reviewed {reviewed} {reviewed === 1 ? 'card' : 'cards'}. Nice
          work.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex items-center gap-3">
        <Button variant="outline" onClick={onReviewMore}>
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
          Check for more
        </Button>
        <Button asChild>
          <Link to="/generate">Generate more</Link>
        </Button>
      </CardContent>
    </Card>
  );
}
