import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// The page composes four data hooks; mock them so the render tests drive each branch directly and
// stay network-free. The pure helpers (formatDayLine/greetingForHour/dueTotals) stay real.
const { useDashboardTiles } = vi.hoisted(() => ({
  useDashboardTiles: vi.fn(),
}));
vi.mock('@/lib/dashboard', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/dashboard')>();
  return { ...actual, useDashboardTiles };
});
const { useDueQuery } = vi.hoisted(() => ({ useDueQuery: vi.fn() }));
vi.mock('@/lib/review', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/review')>();
  return { ...actual, useDueQuery };
});
const { useSettingsQuery } = vi.hoisted(() => ({ useSettingsQuery: vi.fn() }));
vi.mock('@/lib/settings', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/settings')>();
  return { ...actual, useSettingsQuery };
});
const { useFeatureFlag } = vi.hoisted(() => ({ useFeatureFlag: vi.fn() }));
vi.mock('@/lib/feature-flags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/feature-flags')>();
  return { ...actual, useFeatureFlag };
});

import {
  ActiveLanguageContext,
  type ActiveLanguageState,
} from '@/components/active-language-context';
import type { LanguageTileModel } from '@/lib/dashboard';
import type { LanguageOut } from '@/lib/languages';
import type { CardOut, DueResponse } from '@/lib/review';
import Dashboard from '@/pages/Dashboard';

const SPANISH: LanguageOut = {
  id: 1,
  name: 'Spanish',
  code: 'es',
  vowelized: false,
};
const HEBREW: LanguageOut = {
  id: 3,
  name: 'Hebrew',
  code: 'he',
  vowelized: true,
};
const FRENCH: LanguageOut = {
  id: 7,
  name: 'French',
  code: 'fr',
  vowelized: false,
};
const ITALIAN: LanguageOut = {
  id: 9,
  name: 'Italian',
  code: 'it',
  vowelized: false,
};

function makeCards(count: number): CardOut[] {
  return Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    language_id: 1,
    direction: 'recognition',
    front: 'f',
    back: 'b',
    used_words: null,
    word_explanations: null,
    gen_level: null,
    saved: true,
    due: null,
  }));
}

/** A `useDueQuery` result stub (only the fields TodayHero reads). */
function dueResult(overrides: {
  isPending?: boolean;
  isError?: boolean;
  data?: DueResponse;
  refetch?: () => void;
}) {
  return {
    isPending: false,
    isError: false,
    data: undefined,
    refetch: vi.fn(),
    ...overrides,
  };
}

function makeTile(
  overrides: Partial<LanguageTileModel> & { language: LanguageOut },
): LanguageTileModel {
  return {
    isActive: false,
    totals: { due: 0, fresh: 0, total: 0 },
    dueLoading: false,
    dueError: false,
    band: 'A1',
    progress: 0.2,
    ...overrides,
  };
}

function makeValue(
  overrides: Partial<ActiveLanguageState> = {},
): ActiveLanguageState {
  return {
    languages: [SPANISH],
    activeLanguageId: 1,
    activeLanguage: SPANISH,
    setActiveLanguageId: vi.fn(),
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    ...overrides,
  };
}

function renderDashboard(value: ActiveLanguageState = makeValue()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ActiveLanguageContext.Provider value={value}>
          <Dashboard />
        </ActiveLanguageContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  // Defaults: a ready hero (3 cards), one language tile, empty settings, WordOfTheDay flag off.
  useDueQuery.mockReturnValue(
    dueResult({ data: { due: makeCards(2), new: makeCards(1) } }),
  );
  useDashboardTiles.mockReturnValue([
    makeTile({
      language: SPANISH,
      isActive: true,
      totals: { due: 2, fresh: 1, total: 3 },
      band: 'B1',
    }),
  ]);
  useSettingsQuery.mockReturnValue({ data: { values: {} } });
  useFeatureFlag.mockReturnValue(false);
});

describe('Dashboard header', () => {
  it('renders the pinned h1 "Dashboard" with the greeting/date in a sibling, never the h1', () => {
    renderDashboard();
    const heading = screen.getByRole('heading', { name: 'Dashboard' });
    // Byte-identical to the nav label — the greeting must NOT leak into the h1.
    expect(heading.textContent).toBe('Dashboard');
    expect(
      screen.getByText(/Good (morning|afternoon|evening|night)\./),
    ).toBeInTheDocument();
  });
});

describe('Today hero', () => {
  it('shows the count-up total, the due/new breakdown, and Start review', () => {
    // Tile total (5) differs from the hero total (3) so "3" is unambiguously the hero count.
    useDashboardTiles.mockReturnValue([
      makeTile({ language: SPANISH, totals: { due: 5, fresh: 0, total: 5 } }),
    ]);
    renderDashboard();

    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('cards ready')).toBeInTheDocument();
    expect(screen.getByText('2 due · 1 new')).toBeInTheDocument();
    const start = screen.getByRole('link', { name: 'Start review' });
    expect(start).toHaveAttribute('href', '/review');
  });

  it('renders the zero state with generate + discover when nothing is due', () => {
    useDueQuery.mockReturnValue(dueResult({ data: { due: [], new: [] } }));
    renderDashboard();

    expect(screen.getByText("You're all caught up")).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Generate sentences' }),
    ).toHaveAttribute('href', '/generate');
    expect(
      screen.getByRole('link', { name: 'Discover words' }),
    ).toHaveAttribute('href', '/discover');
    expect(
      screen.queryByRole('link', { name: 'Start review' }),
    ).not.toBeInTheDocument();
  });

  it('renders a loading skeleton while the due batch is pending', () => {
    useDueQuery.mockReturnValue(dueResult({ isPending: true }));
    renderDashboard();

    expect(
      screen.getByRole('heading', { name: 'Dashboard' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'Start review' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("You're all caught up")).not.toBeInTheDocument();
  });

  it('renders a retryable error state when the due batch fails', () => {
    const refetch = vi.fn();
    useDueQuery.mockReturnValue(dueResult({ isError: true, refetch }));
    renderDashboard();

    expect(screen.getByText(/Couldn't load today's cards/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(refetch).toHaveBeenCalled();
  });

  it('shows the daily-limits footnote linking to Settings', () => {
    useSettingsQuery.mockReturnValue({
      data: { values: { daily_new_limit: '8', daily_total_limit: '40' } },
    });
    renderDashboard();

    const footnote = screen.getByRole('link', { name: /Daily limits/ });
    expect(footnote).toHaveAttribute('href', '/settings');
    expect(footnote).toHaveTextContent('Daily limits: 8 new · 40 total');
  });
});

describe('Language tiles', () => {
  it('renders a tile per language with due badges, band chips, and the active chip', () => {
    useDashboardTiles.mockReturnValue([
      makeTile({
        language: SPANISH,
        isActive: true,
        totals: { due: 1, fresh: 2, total: 3 },
        band: 'B1',
      }),
      makeTile({
        language: HEBREW,
        totals: { due: 0, fresh: 0, total: 0 },
        band: 'A1',
      }),
      makeTile({
        language: FRENCH,
        totals: null,
        dueLoading: true,
        band: null,
      }),
      makeTile({
        language: ITALIAN,
        totals: null,
        dueError: true,
        band: 'A2',
      }),
    ]);
    renderDashboard(
      makeValue({ languages: [SPANISH, HEBREW, FRENCH, ITALIAN] }),
    );

    // A link per language, routing to Review.
    expect(screen.getByRole('link', { name: /Spanish/ })).toHaveAttribute(
      'href',
      '/review',
    );
    expect(screen.getByRole('link', { name: /Hebrew/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /French/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Italian/ })).toBeInTheDocument();
    // Due badges: n>0 → "{n} ready", n===0 → "Done".
    expect(screen.getByText('3 ready')).toBeInTheDocument();
    expect(screen.getByText('Done')).toBeInTheDocument();
    // An errored due batch degrades to a muted dash (not a perpetual loading skeleton).
    expect(screen.getByText('—')).toBeInTheDocument();
    // Band chips + active chip.
    expect(screen.getByText('B1')).toBeInTheDocument();
    expect(screen.getByText('A1')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    // Manage link.
    expect(screen.getByRole('link', { name: 'Manage' })).toHaveAttribute(
      'href',
      '/languages',
    );
  });

  it('sets a language active and routes to Review when its tile is tapped', () => {
    const setActiveLanguageId = vi.fn();
    useDashboardTiles.mockReturnValue([
      makeTile({
        language: HEBREW,
        totals: { due: 2, fresh: 0, total: 2 },
        band: 'A1',
      }),
    ]);
    renderDashboard(
      makeValue({
        languages: [HEBREW],
        activeLanguageId: 3,
        activeLanguage: HEBREW,
        setActiveLanguageId,
      }),
    );

    const tile = screen.getByRole('link', { name: /Hebrew/ });
    expect(tile).toHaveAttribute('href', '/review');
    fireEvent.click(tile);
    expect(setActiveLanguageId).toHaveBeenCalledWith(3);
  });
});

describe('Quick actions', () => {
  it('links to Generate and Discover', () => {
    renderDashboard();
    expect(
      screen.getByRole('link', { name: /Turn your words into sentences/ }),
    ).toHaveAttribute('href', '/generate');
    expect(
      screen.getByRole('link', { name: /Let Lengua pick new words/ }),
    ).toHaveAttribute('href', '/discover');
  });
});

describe('Fresh user', () => {
  it('collapses to the onboarding empty-state, hiding hero/tiles/actions', () => {
    renderDashboard(
      makeValue({
        languages: [],
        activeLanguageId: null,
        activeLanguage: null,
      }),
    );

    const empty = screen.getByTestId('empty-state');
    expect(within(empty).getByText('Welcome to Lengua')).toBeInTheDocument();
    expect(
      within(empty).getByText('Generate sentences from your words'),
    ).toBeInTheDocument();
    expect(
      within(empty).getByRole('link', { name: 'Add a language' }),
    ).toHaveAttribute('href', '/languages');
    // Nothing else from the loaded dashboard renders.
    expect(
      screen.queryByRole('link', { name: 'Start review' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('Turn your words into sentences'),
    ).not.toBeInTheDocument();
  });
});

describe('Languages loading + error', () => {
  it('renders skeletons (no onboarding, no hero) while languages load', () => {
    renderDashboard(
      makeValue({ isLoading: true, languages: [], activeLanguageId: null }),
    );
    expect(
      screen.getByRole('heading', { name: 'Dashboard' }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('empty-state')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'Start review' }),
    ).not.toBeInTheDocument();
  });

  it('renders a retryable error when the language list fails', () => {
    const refetch = vi.fn();
    renderDashboard(makeValue({ isError: true, refetch }));

    expect(
      screen.getByText(/Couldn't load your languages/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(refetch).toHaveBeenCalled();
  });
});
