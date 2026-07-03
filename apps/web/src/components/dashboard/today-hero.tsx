/**
 * Dashboard "Today" hero (Apple redesign PR4, spec §5.2) — the calm top card that answers the one
 * question the home screen exists for: how many cards are ready right now, and a big pill to start.
 *
 * Reads the active language's due batch through the EXISTING {@link useDueQuery} (no new endpoint),
 * counts the total up on first mount, and renders one of four states inside the same card frame:
 * loading (skeleton), error (retryable), zero ("all caught up" with generate/discover), or the
 * ready hero (count + "Start review"). The count-up honours reduced motion (settles instantly).
 */
import { m } from 'framer-motion';
import { CheckCircle2 } from 'lucide-react';
import { Link } from 'react-router-dom';

import { ErrorState } from '@/components/error-state';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { dueTotals } from '@/lib/dashboard';
import { useDueQuery } from '@/lib/review';
import { useCountUp } from '@/lib/use-count-up';

export interface TodayHeroProps {
  /** The active language id (or `null` before one resolves — renders the loading skeleton). */
  languageId: number | null;
  /** The active language's display name (for the eyebrow); empty string hides the ` · name`. */
  languageName: string;
  /** The user's daily new-card limit (already resolved to a display string). */
  dailyNew: string;
  /** The user's daily total-card limit (already resolved to a display string). */
  dailyTotal: string;
}

/** The Today hero card, wired to the active language's due batch. */
export function TodayHero({
  languageId,
  languageName,
  dailyNew,
  dailyTotal,
}: TodayHeroProps) {
  const due = useDueQuery(languageId);

  // Disabled (no active language yet) or in flight — the batch skeleton keeps the layout from jumping.
  if (due.isPending) {
    return <Skeleton className="h-36 w-full rounded-2xl" />;
  }

  if (due.isError) {
    return (
      <HeroFrame>
        <ErrorState
          title="Couldn't load today's cards"
          description="Something went wrong loading your due batch."
          onRetry={() => void due.refetch()}
        />
      </HeroFrame>
    );
  }

  const totals = dueTotals(due.data);

  return (
    <HeroFrame>
      {totals.total === 0 ? (
        <HeroCaughtUp />
      ) : (
        <HeroReady
          total={totals.total}
          dueCount={totals.due}
          freshCount={totals.fresh}
          languageName={languageName}
          dailyNew={dailyNew}
          dailyTotal={dailyTotal}
        />
      )}
    </HeroFrame>
  );
}

/** The shared card frame + calm top wash (the rejected gradient slab's HIG-restrained replacement). */
function HeroFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative overflow-hidden rounded-2xl border bg-card p-6 shadow-raised sm:p-8">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-primary/[0.05] to-transparent"
      />
      <div className="relative">{children}</div>
    </div>
  );
}

interface HeroReadyProps {
  total: number;
  dueCount: number;
  freshCount: number;
  languageName: string;
  dailyNew: string;
  dailyTotal: string;
}

/** The primary hero: eyebrow → big count-up → "X due · Y new" → Start review + a limits footnote. */
function HeroReady({
  total,
  dueCount,
  freshCount,
  languageName,
  dailyNew,
  dailyTotal,
}: HeroReadyProps) {
  const count = useCountUp(total, 500);
  return (
    <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
      <div className="space-y-1">
        <p className="text-caption uppercase text-muted-foreground">
          Today{languageName !== '' ? ` · ${languageName}` : ''}
        </p>
        <div className="flex items-baseline gap-2">
          <m.span
            className="text-[2.75rem] font-bold leading-none tracking-[-0.03em] tabular-nums"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.2 }}
          >
            {count}
          </m.span>
          <span className="text-title2">
            {total === 1 ? 'card ready' : 'cards ready'}
          </span>
        </div>
        <p className="text-subhead tabular-nums text-muted-foreground">
          {dueCount} due · {freshCount} new
        </p>
        <p className="pt-1">
          <Link
            to="/settings"
            className="text-footnote text-muted-foreground transition-colors hover:text-foreground"
          >
            Daily limits: <span className="tabular-nums">{dailyNew}</span> new ·{' '}
            <span className="tabular-nums">{dailyTotal}</span> total
          </Link>
        </p>
      </div>
      <Button asChild size="lg" className="shrink-0">
        <Link to="/review">Start review</Link>
      </Button>
    </div>
  );
}

/** The zero state: nothing due — celebrate and point at the two ways to add more. */
function HeroCaughtUp() {
  return (
    <div className="flex flex-col items-start gap-4">
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-hig-green/15">
        <CheckCircle2
          className="h-7 w-7 text-hig-green-deep"
          aria-hidden="true"
        />
      </div>
      <div className="space-y-1">
        <p className="text-title2">You&apos;re all caught up</p>
        <p className="text-subhead text-muted-foreground">
          Nothing is due right now. Add more to keep the streak going.
        </p>
      </div>
      <div className="flex flex-wrap gap-3">
        <Button asChild>
          <Link to="/generate">Generate sentences</Link>
        </Button>
        <Button asChild variant="tinted">
          <Link to="/discover">Discover words</Link>
        </Button>
      </div>
    </div>
  );
}
