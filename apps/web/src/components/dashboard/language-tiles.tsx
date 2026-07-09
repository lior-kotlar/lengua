/**
 * Dashboard "Your languages" tile grid (Apple redesign PR4, spec §5.3).
 *
 * One tile per language: name + code chip, a CEFR band chip + progress bar (toward the next band,
 * captioned "{p}% to {next}"), and a due badge ("{due} due · {fresh} new" when cards await, else
 * "Done"). Tapping a tile sets that language
 * active and routes to Review — the fastest path from "which language?" to reviewing it. The active
 * language's tile carries a ring + an "Active" chip. View-models come pre-built from
 * {@link import('@/lib/dashboard').useDashboardTiles} (the existing due + proficiency fan-out).
 */
import { ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Skeleton } from '@/components/ui/skeleton';
import type { DueTotals, LanguageTileModel } from '@/lib/dashboard';
import {
  cefrBandChipClass,
  cefrBandColor,
  nextBand,
  progressPercent,
} from '@/lib/cefr';
import { cn } from '@/lib/utils';

export interface LanguageTilesProps {
  tiles: LanguageTileModel[];
  /** Set a language active (persisted); the tile then routes to /review. */
  onSelectLanguage: (languageId: number) => void;
}

/** The "Your languages" section: a caption header + Manage link over the responsive tile grid. */
export function LanguageTiles({ tiles, onSelectLanguage }: LanguageTilesProps) {
  return (
    <section aria-label="Your languages" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-caption uppercase text-muted-foreground">
          Your languages
        </h2>
        <Link
          to="/languages"
          className="text-subhead font-medium text-primary transition-colors hover:text-primary/80"
        >
          Manage
        </Link>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {tiles.map((tile) => (
          <LanguageTile
            key={tile.language.id}
            tile={tile}
            onSelect={onSelectLanguage}
          />
        ))}
      </div>
    </section>
  );
}

interface LanguageTileProps {
  tile: LanguageTileModel;
  onSelect: (languageId: number) => void;
}

/** One language tile — a link to Review that sets the language active on the way. */
function LanguageTile({ tile, onSelect }: LanguageTileProps) {
  const { language, isActive, totals, dueLoading, band, progress } = tile;
  const percent = progressPercent(progress);
  const upcoming = band !== null ? nextBand(band) : null;

  return (
    <Link
      to="/review"
      onClick={() => onSelect(language.id)}
      className={cn(
        'flex flex-col gap-3 rounded-lg border bg-card p-5 shadow-card transition-all [transition-duration:250ms] ease-apple hover:-translate-y-px hover:shadow-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        isActive && 'ring-1 ring-primary/30',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="truncate text-headline">{language.name}</span>
            {language.code !== null && language.code !== '' && (
              <span className="rounded bg-secondary px-1.5 text-caption uppercase text-muted-foreground">
                {language.code}
              </span>
            )}
          </div>
          {band !== null && (
            <span
              className={cn(
                'inline-flex rounded-full px-2 py-0.5 text-caption font-semibold',
                cefrBandChipClass(band),
              )}
            >
              {band}
            </span>
          )}
        </div>
        {isActive && (
          <span className="shrink-0 rounded-full bg-hig-blue/15 px-2 py-0.5 text-caption font-semibold text-hig-blue-deep">
            Active
          </span>
        )}
      </div>

      {band !== null && (
        <div className="space-y-1">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className={cn('h-full rounded-full', cefrBandColor(band))}
              style={{ width: `${percent}%` }}
            />
          </div>
          <p className="text-footnote text-muted-foreground">
            {upcoming !== null ? (
              <>
                <span className="tabular-nums">{percent}%</span> to {upcoming}
              </>
            ) : (
              'Top level (C2)'
            )}
          </p>
        </div>
      )}

      <div className="mt-auto flex items-center justify-between pt-1">
        <DueBadge totals={totals} loading={dueLoading} error={tile.dueError} />
        <ChevronRight
          className="h-4 w-4 shrink-0 text-muted-foreground"
          aria-hidden="true"
        />
      </div>
    </Link>
  );
}

/**
 * The per-tile due badge: a skeleton while loading, then "{due} due · {fresh} new" (orange) or
 * "Done" (green) — the same breakdown copy the Today hero uses, so a language's tile and hero read
 * identically. On a failed due fetch it degrades to a muted dash (like the band/progress hide on a
 * level error) rather than shimmering forever — the row layout stays intact so the chevron keeps
 * its place.
 */
function DueBadge({
  totals,
  loading,
  error,
}: {
  totals: DueTotals | null;
  loading: boolean;
  error: boolean;
}) {
  if (loading) {
    return <Skeleton className="h-5 w-16 rounded-full" aria-hidden="true" />;
  }
  if (error || totals === null) {
    return (
      <span className="text-caption text-muted-foreground" aria-hidden="true">
        —
      </span>
    );
  }
  if (totals.total > 0) {
    return (
      <span className="rounded-full bg-hig-orange/15 px-2 py-0.5 text-caption font-semibold tabular-nums text-hig-orange-deep">
        {totals.due} due · {totals.fresh} new
      </span>
    );
  }
  return (
    <span className="rounded-full bg-hig-green/15 px-2 py-0.5 text-caption font-semibold text-hig-green-deep">
      Done
    </span>
  );
}
