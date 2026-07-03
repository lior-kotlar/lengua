/**
 * Dashboard data layer (Apple redesign PR4, spec §5) — the home screen's reads over the EXISTING
 * APIs (`GET /review/due`, `GET /proficiency/{id}`), plus the pure presentation helpers the page
 * and its co-located tests build on. No new endpoints.
 *
 * Two shapes of data:
 *  - The **Today hero** reads the active language's due batch through the existing `useDueQuery`
 *    (its own query semantics, unchanged).
 *  - The **per-language tile grid** fans out over every language with {@link useDashboardTiles},
 *    reusing the shared `fetchDue` / `fetchProficiency` fetchers and their cache keys (`dueKey` /
 *    `proficiencyKey`) so a language's due batch + level are fetched under the same cache entry the
 *    hero/CEFR panel already use — never issued twice. The fan-out copies carry a
 *    `staleTime: 60_000`, so switching focus back to the tab doesn't re-hit the API for every
 *    language at once (the Review screen keeps its own, un-capped query semantics because it mounts
 *    its own `useDueQuery`).
 *
 * The number-crunching ({@link dueTotals}) and the tile view-model ({@link buildLanguageTiles}) are
 * pure and dependency-free, so the tile states (loading / ready / empty / active) are unit-tested
 * without React, and the hook is a thin `useQueries` wrapper over them.
 */
import { useQueries } from '@tanstack/react-query';

import type { LanguageOut } from '@/lib/languages';
import { fetchProficiency, proficiencyKey } from '@/lib/proficiency';
import type { ProficiencyOut } from '@/lib/proficiency';
import { dueKey, fetchDue } from '@/lib/review';
import type { DueResponse } from '@/lib/review';

/** How long a dashboard fan-out copy stays fresh before it may refetch on focus (spec §5, resolved risk). */
export const DASHBOARD_STALE_TIME_MS = 60_000;

// ── Pure presentation helpers (unit-tested, cheap coverage) ────────────────────────────────────────

/**
 * The time-of-day greeting shown beside the date line (never in the h1 — that stays "Dashboard").
 *
 * Bands: morning 05–11, afternoon 12–16, evening 17–21, otherwise night. `hour` is a 0–23 local hour.
 */
export function greetingForHour(hour: number): string {
  if (hour >= 5 && hour < 12) {
    return 'Good morning';
  }
  if (hour >= 12 && hour < 17) {
    return 'Good afternoon';
  }
  if (hour >= 17 && hour < 22) {
    return 'Good evening';
  }
  return 'Good night';
}

/** Format a date as the dashboard day line, e.g. `"Thursday, July 2"` (weekday + month + day, en-US). */
export function formatDayLine(date: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  }).format(date);
}

/** The due/new/total counts for a language's batch. */
export interface DueTotals {
  /** Cards that are due for review (previously seen). */
  due: number;
  /** Never-reviewed (fresh) cards. */
  fresh: number;
  /** `due + fresh` — the "cards ready" the hero counts up to. */
  total: number;
}

/**
 * Reduce a due-batch payload to its `{ due, fresh, total }` counts.
 *
 * Defensive against a missing payload (query still loading → all zero) so callers can render a
 * count without a separate guard.
 */
export function dueTotals(response: DueResponse | undefined): DueTotals {
  const due = response?.due?.length ?? 0;
  const fresh = response?.new?.length ?? 0;
  return { due, fresh, total: due + fresh };
}

// ── Per-language tile view-model ───────────────────────────────────────────────────────────────────

/** The minimal query-result shape {@link buildLanguageTiles} reads (a `useQueries` entry satisfies it). */
export interface TileQueryResult<T> {
  data?: T;
  isPending: boolean;
  isError: boolean;
}

/** Everything a language tile renders — derived purely from the language + its two query results. */
export interface LanguageTileModel {
  language: LanguageOut;
  /** True for the currently active language (gets the ring + "Active" chip). */
  isActive: boolean;
  /** The due/new/total counts, or `null` while the due batch is still loading / errored. */
  totals: DueTotals | null;
  /** True while the due batch is in flight (show a loading placeholder, not "Done"). */
  dueLoading: boolean;
  /** True when the due batch failed to load (degrade the badge gracefully, don't shimmer forever). */
  dueError: boolean;
  /** The CEFR band label, or `null` while the level is loading / errored (hide the chip + bar). */
  band: string | null;
  /** The intra-band progress fraction (0..1); `0` when the level is unknown. */
  progress: number;
}

/**
 * Build the tile view-models from the languages and their fanned-out due + proficiency results.
 *
 * Pure — the results arrays are aligned to `languages` by index (that is how {@link useDashboardTiles}
 * constructs them). A language whose level failed/loads degrades to no band chip + an empty bar
 * rather than throwing; a language whose due batch is pending shows a loading badge.
 */
export function buildLanguageTiles(
  languages: readonly LanguageOut[],
  activeLanguageId: number | null,
  dueResults: readonly TileQueryResult<DueResponse>[],
  profResults: readonly TileQueryResult<ProficiencyOut>[],
): LanguageTileModel[] {
  return languages.map((language, index) => {
    const dueResult = dueResults[index];
    const profResult = profResults[index];
    return {
      language,
      isActive: language.id === activeLanguageId,
      totals: dueResult?.data !== undefined ? dueTotals(dueResult.data) : null,
      dueLoading: dueResult?.isPending ?? true,
      dueError: dueResult?.isError ?? false,
      band: profResult?.data?.band ?? null,
      progress: profResult?.data?.progress ?? 0,
    };
  });
}

/**
 * Fan out the due batch + proficiency for every language into the tile view-models (spec §5).
 *
 * Reuses the shared `fetchDue` / `fetchProficiency` fetchers under their canonical cache keys, so the
 * active language's hero query and its tile share one cache entry. The fan-out copies carry
 * {@link DASHBOARD_STALE_TIME_MS} so a focus refetch doesn't hammer the API across every language.
 */
export function useDashboardTiles(
  languages: readonly LanguageOut[],
  activeLanguageId: number | null,
): LanguageTileModel[] {
  const dueResults = useQueries({
    queries: languages.map((language) => ({
      queryKey: dueKey(language.id),
      queryFn: () => fetchDue(language.id),
      staleTime: DASHBOARD_STALE_TIME_MS,
    })),
  });
  const profResults = useQueries({
    queries: languages.map((language) => ({
      queryKey: proficiencyKey(language.id),
      queryFn: () => fetchProficiency(language.id),
      staleTime: DASHBOARD_STALE_TIME_MS,
    })),
  });
  return buildLanguageTiles(
    languages,
    activeLanguageId,
    dueResults,
    profResults,
  );
}
