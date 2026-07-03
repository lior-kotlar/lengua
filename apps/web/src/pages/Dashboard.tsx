/**
 * Dashboard — the real home screen (Apple redesign PR4, spec §5). Replaces the placeholder.
 *
 * Top to bottom: the pinned `<h1>Dashboard</h1>` (byte-identical to the nav label; the greeting +
 * date live in a sibling `<p>`, never the h1) → the Today hero (due count + Start review) → the
 * per-language tile grid → quick actions → the flag-gated Word of the day. A fresh user (no
 * languages) collapses everything below the h1 to one onboarding card. Sections stagger in on mount
 * (reduced-motion-safe via `MotionConfig`). Everything reads the EXISTING APIs — no new endpoints.
 */
import { useMemo } from 'react';
import { m } from 'framer-motion';
import type { Variants } from 'framer-motion';

import { useActiveLanguage } from '@/components/active-language-context';
import { OnboardingCard } from '@/components/dashboard/onboarding-card';
import { LanguageTiles } from '@/components/dashboard/language-tiles';
import { QuickActions } from '@/components/dashboard/quick-actions';
import { TodayHero } from '@/components/dashboard/today-hero';
import { ErrorState } from '@/components/error-state';
import { Skeleton } from '@/components/ui/skeleton';
import { WordOfTheDay } from '@/components/word-of-the-day';
import {
  formatDayLine,
  greetingForHour,
  useDashboardTiles,
} from '@/lib/dashboard';
import {
  DAILY_NEW_LIMIT_KEY,
  DAILY_TOTAL_LIMIT_KEY,
  initialSettingValue,
  SETTINGS_FIELDS,
  useSettingsQuery,
  type SettingsOut,
} from '@/lib/settings';

// Sections stagger in on mount (spec §5.7): parent staggers children, each springs up from y+12.
const CONTAINER_VARIANTS: Variants = {
  show: { transition: { staggerChildren: 0.06 } },
};
const ITEM_VARIANTS: Variants = {
  hidden: { opacity: 0, y: 12 },
  show: {
    opacity: 1,
    y: 0,
    transition: { type: 'spring', stiffness: 300, damping: 28 },
  },
};

/** Resolve a daily-limit setting to its display string (saved value, else the field's fallback). */
function dailyLimit(
  settings: SettingsOut | undefined,
  key: string,
  fallback: number,
): string {
  const field = SETTINGS_FIELDS.find((definition) => definition.key === key);
  return field !== undefined
    ? initialSettingValue(settings, field)
    : String(fallback);
}

export default function Dashboard() {
  const {
    languages,
    activeLanguageId,
    activeLanguage,
    setActiveLanguageId,
    isLoading,
    isError,
    refetch,
  } = useActiveLanguage();
  const settings = useSettingsQuery();
  // One clock read per mount for the greeting/date line (no need to re-tick within a session).
  const now = useMemo(() => new Date(), []);
  const tiles = useDashboardTiles(languages, activeLanguageId);

  const dailyNew = dailyLimit(settings.data, DAILY_NEW_LIMIT_KEY, 10);
  const dailyTotal = dailyLimit(settings.data, DAILY_TOTAL_LIMIT_KEY, 50);

  return (
    <m.div
      className="mx-auto max-w-5xl space-y-8"
      initial="hidden"
      animate="show"
      variants={CONTAINER_VARIANTS}
    >
      <m.header variants={ITEM_VARIANTS} className="space-y-1">
        <h1 className="text-large-title">Dashboard</h1>
        <p className="text-subhead text-muted-foreground">
          {formatDayLine(now)} — {greetingForHour(now.getHours())}.
        </p>
      </m.header>

      {isError ? (
        <m.div variants={ITEM_VARIANTS}>
          <ErrorState
            title="Couldn't load your languages"
            description="Something went wrong loading your languages."
            onRetry={refetch}
          />
        </m.div>
      ) : isLoading ? (
        <m.div variants={ITEM_VARIANTS} className="space-y-8">
          <Skeleton className="h-36 w-full rounded-2xl" />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Skeleton className="h-32 rounded-lg" />
            <Skeleton className="h-32 rounded-lg" />
            <Skeleton className="h-32 rounded-lg" />
          </div>
        </m.div>
      ) : languages.length === 0 ? (
        <m.div variants={ITEM_VARIANTS}>
          <OnboardingCard />
        </m.div>
      ) : (
        <>
          <m.div variants={ITEM_VARIANTS}>
            <TodayHero
              languageId={activeLanguageId}
              languageName={activeLanguage?.name ?? ''}
              dailyNew={dailyNew}
              dailyTotal={dailyTotal}
            />
          </m.div>
          <m.div variants={ITEM_VARIANTS}>
            <LanguageTiles
              tiles={tiles}
              onSelectLanguage={setActiveLanguageId}
            />
          </m.div>
          <m.div variants={ITEM_VARIANTS}>
            <QuickActions />
          </m.div>
          <m.div variants={ITEM_VARIANTS}>
            {/* Experimental, flag-gated — renders nothing until the word_of_the_day flag is on. */}
            <WordOfTheDay />
          </m.div>
        </>
      )}
    </m.div>
  );
}
