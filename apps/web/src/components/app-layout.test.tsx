/**
 * Shell/navigation contract tests (redesign PR2, spec §4):
 *  - exactly ONE `navigation` landmark named "Primary" (jsdom sees both of its lists; Playwright's
 *    role engine excludes whichever is display-hidden per viewport),
 *  - the desktop sidebar list and the mobile tab bar list are both inside that single landmark,
 *  - the header banner keeps the pinned wordmark link and the at-mount "Sign out" button.
 *
 * NOTE for future tests: both nav lists render in jsdom, so any query for a nav link must scope
 * with `within(screen.getByTestId('nav-desktop'))` (or 'nav-mobile').
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/components/auth-context', () => ({ useAuth }));

const { useLanguagesQuery } = vi.hoisted(() => ({
  useLanguagesQuery: vi.fn(),
}));
vi.mock('@/lib/languages', () => ({
  useLanguagesQuery,
  languagesKey: ['languages'],
}));

const { useProficiencyQuery, useSetProficiencyBand } = vi.hoisted(() => ({
  useProficiencyQuery: vi.fn(),
  useSetProficiencyBand: vi.fn(),
}));
vi.mock('@/lib/proficiency', () => ({
  useProficiencyQuery,
  useSetProficiencyBand,
  proficiencyKey: (id: number) => ['proficiency', id],
}));

import { AppLayout } from '@/components/app-layout';
import { NAV_ITEMS } from '@/components/nav-items';
import { ThemeProvider } from '@/components/theme-provider';

function renderShell(initialPath = '/') {
  return render(
    <ThemeProvider defaultTheme="light">
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="*" element={<div>Page body</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({
    user: { id: 'u1', email: 'demo@lengua.test' },
    session: {},
    loading: false,
  });
  // An empty account keeps the picker/CEFR panel in their no-language states (no proficiency query).
  useLanguagesQuery.mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  });
  useProficiencyQuery.mockReturnValue({
    data: { band: 'B1', progress: 0.4, score: 2.4 },
    isLoading: false,
    isError: false,
  });
  useSetProficiencyBand.mockReturnValue({ mutate: vi.fn(), isPending: false });
});

describe('AppLayout navigation landmark', () => {
  it('renders exactly one navigation named "Primary"', () => {
    renderShell();
    expect(screen.getAllByRole('navigation', { name: 'Primary' })).toHaveLength(
      1,
    );
  });

  it('puts the full destination list in the desktop sidebar list', () => {
    renderShell();
    const desktop = within(screen.getByTestId('nav-desktop'));
    for (const { to, label } of NAV_ITEMS) {
      expect(desktop.getByRole('link', { name: label })).toHaveAttribute(
        'href',
        to,
      );
    }
  });

  it('puts the four core destinations + a More dialog trigger in the mobile tab bar list', () => {
    renderShell();
    const mobile = within(screen.getByTestId('nav-mobile'));
    for (const label of ['Dashboard', 'Generate', 'Review', 'Discover']) {
      expect(mobile.getByRole('link', { name: label })).toBeInTheDocument();
    }
    // Languages/Settings/Account are NOT bar slots — they live in the More sheet.
    expect(mobile.queryByRole('link', { name: 'Languages' })).toBeNull();
    const more = mobile.getByRole('button', { name: 'More' });
    expect(more).toHaveAttribute('aria-haspopup', 'dialog');
    // Both lists live inside the single Primary landmark.
    const nav = screen.getByRole('navigation', { name: 'Primary' });
    expect(nav).toContainElement(screen.getByTestId('nav-desktop'));
    expect(nav).toContainElement(screen.getByTestId('nav-mobile'));
  });

  it('keeps both CEFR override selects labeled when the More sheet is open (no duplicate ids)', async () => {
    // With an active language the CefrPanel mounts TWICE at once: the (CSS-hidden) desktop sidebar
    // copy and the open More sheet copy. Each must keep its own label→select association.
    useLanguagesQuery.mockReturnValue({
      data: [{ id: 7, name: 'Spanish', code: 'es', vowelized: false }],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    const user = userEvent.setup();
    renderShell();

    await user.click(screen.getByRole('button', { name: 'More' }));

    // The sheet's (visible) select resolves its accessible name through its own label. While the
    // sheet is open Radix marks the app root aria-hidden, so this is the one users interact with.
    const sheet = screen.getByRole('dialog', { name: 'More' });
    const sheetSelect = within(sheet).getByLabelText('Override level');

    // Both simultaneously-mounted panels keep their own label→select association — a shared
    // hardcoded id made BOTH labels target the first (display-hidden) select in tree order.
    const labels = Array.from(document.querySelectorAll('label')).filter(
      (l) => l.textContent === 'Override level',
    ) as HTMLLabelElement[];
    expect(labels).toHaveLength(2);
    const targets = labels.map((l) => l.control);
    expect(targets[0]).not.toBeNull();
    expect(targets[1]).not.toBeNull();
    expect(targets[0]).not.toBe(targets[1]);
    expect(targets).toContain(sheetSelect);
  });

  it('marks the active route in both lists (aria-current)', () => {
    renderShell('/review');
    const desktop = within(screen.getByTestId('nav-desktop'));
    const mobile = within(screen.getByTestId('nav-mobile'));
    expect(desktop.getByRole('link', { name: 'Review' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(mobile.getByRole('link', { name: 'Review' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(
      desktop.getByRole('link', { name: 'Dashboard' }),
    ).not.toHaveAttribute('aria-current');
  });
});

describe('AppLayout header', () => {
  it('keeps the pinned banner contract: wordmark link + at-mount Sign out button', () => {
    renderShell();
    const banner = within(screen.getByRole('banner'));
    expect(banner.getByRole('link', { name: 'Lengua' })).toBeInTheDocument();
    expect(
      banner.getByRole('button', { name: /sign out/i }),
    ).toBeInTheDocument();
    expect(
      banner.getByRole('button', { name: 'Account menu' }),
    ).toBeInTheDocument();
  });

  it('renders the routed page content', () => {
    renderShell();
    expect(screen.getByText('Page body')).toBeInTheDocument();
  });
});
