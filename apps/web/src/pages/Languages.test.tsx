import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { LanguageOut } from '@/lib/languages';

// Stub the heavy children (they have their own tests + hooks); the page test focuses on list /
// empty / loading / error states and the active-language wiring.
vi.mock('@/components/add-language-form', () => ({
  AddLanguageForm: ({
    onCreated,
  }: {
    onCreated?: (language: LanguageOut) => void;
  }) => (
    <button
      onClick={() =>
        onCreated?.({ id: 99, name: 'New', code: null, vowelized: false })
      }
    >
      stub-add
    </button>
  ),
}));
vi.mock('@/components/remove-language-dialog', () => ({
  RemoveLanguageDialog: ({ language }: { language: LanguageOut }) => (
    <span>stub-remove-{language.id}</span>
  ),
}));

import {
  ActiveLanguageContext,
  type ActiveLanguageState,
} from '@/components/active-language-context';
import Languages from '@/pages/Languages';

const LANGS: LanguageOut[] = [
  { id: 1, name: 'Spanish', code: 'es', vowelized: false },
  { id: 2, name: 'French', code: null, vowelized: false },
  // Not in the curated list → carries the "Experimental" badge (issue #95).
  { id: 3, name: 'Klingon', code: 'tlh', vowelized: false },
];

function makeValue(
  overrides: Partial<ActiveLanguageState> = {},
): ActiveLanguageState {
  return {
    languages: LANGS,
    activeLanguageId: 1,
    activeLanguage: LANGS[0],
    setActiveLanguageId: vi.fn(),
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    ...overrides,
  };
}

function renderPage(value: ActiveLanguageState) {
  return render(
    <ActiveLanguageContext.Provider value={value}>
      <Languages />
    </ActiveLanguageContext.Provider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('Languages page', () => {
  it('shows a loading state', () => {
    renderPage(makeValue({ languages: [], isLoading: true }));
    expect(screen.getByText(/loading languages/i)).toBeInTheDocument();
  });

  it('shows an error state', () => {
    renderPage(makeValue({ languages: [], isError: true }));
    expect(screen.getByRole('alert')).toHaveTextContent(/couldn.t load/i);
  });

  it('shows the empty state with no languages, then hides it once some exist', () => {
    const { rerender } = renderPage(makeValue({ languages: [] }));
    expect(
      screen.getByText(/haven.t added any languages yet/i),
    ).toBeInTheDocument();

    rerender(
      <ActiveLanguageContext.Provider value={makeValue()}>
        <Languages />
      </ActiveLanguageContext.Provider>,
    );
    expect(
      screen.queryByText(/haven.t added any languages yet/i),
    ).not.toBeInTheDocument();
    expect(screen.getByText('Spanish')).toBeInTheDocument();
    expect(screen.getByText('French')).toBeInTheDocument();
  });

  it('renders each language with a remove control and marks the active one', () => {
    renderPage(makeValue());
    expect(screen.getByText('stub-remove-1')).toBeInTheDocument();
    expect(screen.getByText('stub-remove-2')).toBeInTheDocument();
    // The active language (id 1) carries the "Active" chip.
    expect(screen.getByText('Active')).toBeInTheDocument();
    // The code badge shows for Spanish (code "es") but not French (null code).
    expect(screen.getByText('es')).toBeInTheDocument();
    // Each row has a two-letter avatar (from the code, else the name): Spanish "es" → ES, French → FR.
    expect(screen.getByText('ES')).toBeInTheDocument();
    expect(screen.getByText('FR')).toBeInTheDocument();
  });

  it('badges only the non-curated (experimental) languages', () => {
    renderPage(makeValue());
    // Klingon (id 3) is not in the curated list → one "Experimental" badge, on that row only.
    const badges = screen.getAllByText('Experimental');
    expect(badges).toHaveLength(1);
    // Sanity: the curated Spanish/French rows carry no badge.
    const spanishRow = screen.getByText('Spanish').closest('li');
    expect(spanishRow).not.toBeNull();
    expect(
      within(spanishRow as HTMLElement).queryByText('Experimental'),
    ).not.toBeInTheDocument();
    const klingonRow = screen.getByText('Klingon').closest('li');
    expect(
      within(klingonRow as HTMLElement).getByText('Experimental'),
    ).toBeInTheDocument();
  });

  it('exposes exactly one heading — the h1 equal to the nav label (the "Your languages" eyebrow is not a heading)', () => {
    // Guards the staging navigateTo contract: getByRole('heading', { name: 'Languages' }) must be
    // unambiguous. A caption rendered as a heading whose name contains "Languages" (e.g. an
    // <h2>Your languages</h2>) would collide with the page <h1> under substring name matching.
    renderPage(makeValue());
    const headings = screen.getAllByRole('heading');
    expect(headings).toHaveLength(1);
    expect(headings[0]).toHaveTextContent('Languages');
    expect(
      screen.getByRole('heading', { name: 'Languages' }),
    ).toBeInTheDocument();
  });

  it('clicking a language makes it active', async () => {
    const value = makeValue();
    renderPage(value);

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /French/ }));

    expect(value.setActiveLanguageId).toHaveBeenCalledWith(2);
  });

  it('selects a newly created language as active', async () => {
    const value = makeValue();
    renderPage(value);

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'stub-add' }));

    expect(value.setActiveLanguageId).toHaveBeenCalledWith(99);
  });
});
