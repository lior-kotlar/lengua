/**
 * Review screen (group 4.6) — the React port of the legacy Streamlit review page.
 *
 * Flow: load the active language's due batch (`GET /review/due`, split into new vs. due), walk it
 * one card at a time — show the prompt (front), reveal the answer (back; the production card's
 * target sentence is tap-a-word enabled), then rate Again/Hard/Good/Easy in the LOCKED
 * red/orange/blue/green colours, which `POST`s the FSRS grade and advances. Keyboard shortcuts make
 * desktop review fast: space/enter reveals, 1–4 rate. When the batch is empty (or fully reviewed)
 * a clean "all caught up" state shows instead.
 *
 * Motion (Apple redesign PR3, spec §6): the active card sits on a static two-card ghost deck and
 * enters/exits with a Y-axis spring (RTL-safe by construction); revealing plays a three-beat
 * cascade (hairline draws from the reading edge → answer fades up → rating pills stagger); grading
 * flashes the chosen pill solid; finishing the batch celebrates with a drawn checkmark + count-up.
 * All exits are ≤180ms so the e2e suite never waits on animation.
 */
import { forwardRef, useCallback, useEffect, useMemo, useState } from 'react';
import { AnimatePresence, m, useIsPresent } from 'framer-motion';
import { CheckCircle2, RotateCcw } from 'lucide-react';
import { Link } from 'react-router-dom';

import { useActiveLanguage } from '@/components/active-language-context';
import { EmptyState } from '@/components/empty-state';
import { ErrorState } from '@/components/error-state';
import { LanguageText } from '@/components/language-text';
import { LoadingState } from '@/components/loading-state';
import { TappableSentence } from '@/components/tappable-sentence';
import { Button } from '@/components/ui/button';
import { Kbd } from '@/components/ui/kbd';
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
  ratingFlashClass,
  useDueQuery,
  useGradeCard,
  type CardOut,
} from '@/lib/review';
import { useCountUp } from '@/lib/use-count-up';
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
        <h1 className="text-large-title">Review</h1>
        <p className="text-subhead text-muted-foreground">
          Review your due flashcards
          {activeLanguage !== null ? ` in ${activeLanguage.name}` : ''}.
        </p>
      </div>

      {/* Right-aligned utility row: the vowel-marks switch self-gates to vocalized languages. */}
      <div className="flex justify-end">
        <VowelMarksToggle />
      </div>

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
  // The rating just committed (1..4), or null. Drives the commit flash + sibling dim; cleared when
  // the card advances or grading fails.
  const [flashRating, setFlashRating] = useState<number | null>(null);

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
    setFlashRating(null);
    setIndex((value) => value + 1);
  }, []);

  const submitGrade = useCallback(
    (rating: number) => {
      if (current === null || grade.isPending) {
        return;
      }
      // Commit flash: the chosen pill fills solid immediately — the 150ms colour transition visually
      // covers the grade round-trip, so there is no artificial delay. Shared by clicks AND keys 1–4.
      setFlashRating(rating);
      // Optional haptic, touch devices only (no-op on desktop/keyboard; Capacitor-ready).
      if (window.matchMedia('(pointer: coarse)').matches) {
        navigator.vibrate?.(10);
      }
      grade.mutate(
        { cardId: current.id, rating },
        {
          onSuccess: advance,
          onError: (error) => {
            setFlashRating(null);
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
    setFlashRating(null);
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

  // Cards still on the deck (including the active one) → how many ghost cards peek out behind it.
  const remaining = batch.length - index;

  return (
    <div className="space-y-4">
      <ReviewProgress
        newCount={due.data.new.length}
        dueCount={due.data.due.length}
        reviewed={index}
        total={batch.length}
      />
      <div className="relative">
        {/* Ghost deck: static, aria-hidden cards stacked behind (Y-axis only → RTL-safe). */}
        {remaining >= 2 && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 translate-y-[10px] scale-[0.97] rounded-2xl border bg-card opacity-60 shadow-card"
          />
        )}
        {remaining >= 3 && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 translate-y-[20px] scale-[0.94] rounded-2xl border bg-card opacity-30 shadow-card"
          />
        )}
        <AnimatePresence mode="popLayout">
          <DeckCard
            // Fresh card component (and tap-a-word state) per card; keyed so the deck springs on swap.
            key={current.id}
            card={current}
            language={language}
            revealed={revealed}
            grading={grade.isPending}
            flashRating={flashRating}
            showVowels={showVowels}
            onReveal={reveal}
            onGrade={submitGrade}
          />
        </AnimatePresence>
      </div>
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
        className="flex items-center justify-between text-subhead tabular-nums"
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
        {/* CSS width transition (no framer) — the progress bar just eases to its new width. */}
        <div
          className="h-full rounded-full bg-primary transition-[width] [transition-duration:400ms] ease-apple"
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
  flashRating: number | null;
  showVowels: boolean;
  onReveal: () => void;
  onGrade: (rating: number) => void;
}

/**
 * The active card in the deck — wraps {@link ReviewCard} in the spring-in / spring-out `m.div`.
 *
 * While a card animates OUT (a newer card took its place), framer keeps the old, frozen subtree
 * mounted for the ~160ms exit and flips its presence to false. We hide that outgoing card from the
 * accessibility/role tree + pointer events for the duration (the ghost-deck divs get the same
 * treatment), so its still-mounted, still-revealed rating pills never collide with the incoming
 * card's — otherwise a role query (or a click) would match two "Good" buttons mid-exit and a
 * strict Playwright assertion would fail. In jsdom the mocked AnimatePresence has no presence
 * context, so `useIsPresent` returns true and the card renders normally.
 *
 * We read presence with `useIsPresent` (read-only), NOT `usePresence`: the latter *registers* this
 * component with AnimatePresence and then blocks it from unmounting until its `safeToRemove` is
 * called. Since we only want the boolean (and never call `safeToRemove`), `usePresence` left every
 * graded card mounted forever — invisible opacity-0 blocks that stacked up in normal flow and grew
 * a white gap above the live card each review. `useIsPresent` just reads the flag and lets the
 * `m.div`'s own exit drive removal (and popLayout's out-of-flow positioning).
 *
 * `forwardRef` is REQUIRED, not incidental: with `mode="popLayout"` AnimatePresence pops the
 * exiting card to `position: absolute` (so the incoming card takes its slot instantly) by MEASURING
 * it through a ref it attaches to its direct child. That child is this component, so if we don't
 * forward the ref down to the `m.div`'s DOM node the measurement silently finds nothing, the pop is
 * skipped, and the outgoing card stays in normal flow for its ~160ms exit — briefly pushing the
 * incoming card below it before it snaps up (a visible one-beat downward flash on every grade).
 */
const DeckCard = forwardRef<HTMLDivElement, ReviewCardProps>(
  function DeckCard(props, ref) {
    const isPresent = useIsPresent();
    return (
      <m.div
        ref={ref}
        initial={{ opacity: 0, y: 12, scale: 0.98 }}
        animate={{
          opacity: 1,
          y: 0,
          scale: 1,
          transition: { type: 'spring', stiffness: 380, damping: 30 },
        }}
        exit={{
          opacity: 0,
          y: -16,
          scale: 0.97,
          transition: { duration: 0.16, ease: [0.4, 0, 1, 1] },
        }}
        aria-hidden={isPresent ? undefined : true}
        className={cn(
          'relative rounded-2xl border bg-card text-card-foreground shadow-raised',
          !isPresent && 'pointer-events-none',
        )}
      >
        <ReviewCard {...props} />
      </m.div>
    );
  },
);

/** One review card: prompt (front), reveal control, then the answer + rating buttons. */
function ReviewCard({
  card,
  language,
  revealed,
  grading,
  flashRating,
  showVowels,
  onReveal,
  onGrade,
}: ReviewCardProps) {
  const production = isProductionCard(card);
  const dir = directionForCode(language.code);
  const languageName = language.name;
  const promptLabel = production
    ? `Build the sentence${languageName !== '' ? ` in ${languageName}` : ''}`
    : 'Read and understand';
  const revealLabel = production ? 'Show answer' : 'Show translation';

  return (
    <div className="p-6">
      <div className="space-y-1.5">
        {/* Prompt label as a caption eyebrow — uppercased in CSS, DOM text intact. */}
        <p className="text-caption uppercase text-muted-foreground">
          {promptLabel}
        </p>
        {/* The prompt is target text for recognition cards (read it) and English for production
            cards (build it) — only the former gets direction/font/diacritics treatment. */}
        <p className="text-[clamp(1.5rem,1.25rem+1vw,1.75rem)] font-medium leading-[1.45] tracking-[-0.014em]">
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
        </p>
      </div>

      {!revealed ? (
        <div className="mt-6">
          <Button className="h-11 px-6" onClick={onReveal}>
            {revealLabel}
            <Kbd>Space</Kbd>
          </Button>
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          {/* Beat 1 — the hairline draws in from the reading-direction edge. */}
          <m.div
            className="h-px bg-border"
            initial={{ scaleX: 0 }}
            animate={{ scaleX: 1 }}
            transition={{ duration: 0.2, ease: [0.32, 0.72, 0, 1] }}
            style={{ transformOrigin: dir === 'rtl' ? 'right' : 'left' }}
          />
          {/* Beat 2 — the answer fades up (opacity/transform only; the prompt never moves). */}
          <m.div
            data-testid="card-answer"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, ease: [0.32, 0.72, 0, 1] }}
          >
            {production ? (
              <TappableSentence
                cardId={card.id}
                text={card.back}
                translation={card.front}
                language={language}
                explanations={card.word_explanations}
                showVowels={showVowels}
              />
            ) : (
              // A recognition card's answer is the ENGLISH translation, so render it as plain text —
              // exactly like a production card's English front (`card.front`) above. Only
              // target-language text gets LanguageText's direction/script-font/diacritics; passing
              // English through it forced an RTL deck's answer into the script font + dir="rtl",
              // which hid it. The recognition PROMPT (target text) keeps its LanguageText.
              <p className="text-[1.25rem] font-medium leading-7">
                {card.back}
              </p>
            )}
            {production && (
              <p className="mt-1 text-xs text-muted-foreground">
                Tap any word for a quick explanation.
              </p>
            )}
          </m.div>
          {/* Beat 3 — the rating pills stagger in. */}
          <RatingButtons
            onGrade={onGrade}
            disabled={grading}
            flashRating={flashRating}
          />
        </div>
      )}
    </div>
  );
}

interface RatingButtonsProps {
  onGrade: (rating: number) => void;
  disabled: boolean;
  flashRating: number | null;
}

/** The four FSRS rating buttons in their LOCKED colours, with their keyboard digit. */
function RatingButtons({ onGrade, disabled, flashRating }: RatingButtonsProps) {
  return (
    <m.div
      role="group"
      aria-label="Rate this card"
      className="grid grid-cols-2 gap-2 sm:grid-cols-4"
      initial="hidden"
      animate="show"
      variants={{ show: { transition: { staggerChildren: 0.03 } } }}
    >
      {RATINGS.map((rating) => {
        const flashed = flashRating === rating.value;
        const dimmed = flashRating !== null && !flashed;
        return (
          <m.div
            key={rating.value}
            variants={{
              hidden: { opacity: 0, y: 8 },
              show: { opacity: 1, y: 0, transition: { duration: 0.2 } },
            }}
          >
            <button
              type="button"
              onClick={() => onGrade(rating.value)}
              disabled={disabled}
              data-rating={rating.value}
              className={cn(
                'flex h-11 w-full items-center justify-center gap-1.5 rounded-full border text-body font-semibold transition-[background-color,border-color,color,transform] duration-150 ease-apple active:scale-[0.96] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50',
                // The just-pressed pill fills solid; its siblings recede.
                flashed
                  ? ratingFlashClass(rating.color)
                  : ratingButtonClass(rating.color),
                dimmed && 'opacity-40 transition-opacity duration-150',
              )}
            >
              {rating.label}
              <Kbd>{rating.value}</Kbd>
            </button>
          </m.div>
        );
      })}
    </m.div>
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

/** Reached the end of the loaded batch — celebrate, then offer to re-check or generate. */
function SessionComplete({ reviewed, onReviewMore }: SessionCompleteProps) {
  const count = useCountUp(reviewed);
  return (
    <div className="rounded-2xl border bg-card p-8 text-center text-card-foreground shadow-raised">
      {/* Spring-in circle with a drawn checkmark (pathLength) — the little "done" moment. */}
      <m.div
        className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-hig-green/15"
        initial={{ scale: 0.5, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: 'spring', stiffness: 260, damping: 20 }}
      >
        <svg
          viewBox="0 0 24 24"
          className="h-7 w-7"
          fill="none"
          stroke="hsl(var(--hig-green-deep))"
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <m.path
            d="M5 13l4 4L19 7"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 0.4, ease: 'easeOut', delay: 0.12 }}
          />
        </svg>
      </m.div>
      <p className="mt-4 text-title1">Done for today</p>
      <p className="mt-1 text-subhead tabular-nums text-muted-foreground">
        You reviewed {count} {reviewed === 1 ? 'card' : 'cards'}. Nice work.
      </p>
      <div className="mt-6 flex items-center justify-center gap-3">
        <Button variant="outline" onClick={onReviewMore}>
          <RotateCcw aria-hidden="true" />
          Check for more
        </Button>
        <Button asChild>
          <Link to="/generate">Generate more</Link>
        </Button>
      </div>
    </div>
  );
}
