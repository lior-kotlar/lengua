import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ActiveLanguageContext,
  type ActiveLanguageState,
} from '@/components/active-language-context';
import { MoreSheet } from '@/components/more-sheet';
import { ThemeProvider } from '@/components/theme-provider';

// The sheet mounts the CefrPanel; a no-language state keeps it off the proficiency query.
const NO_LANGUAGES: ActiveLanguageState = {
  languages: [],
  activeLanguageId: null,
  activeLanguage: null,
  setActiveLanguageId: vi.fn(),
  isLoading: false,
  isError: false,
  refetch: vi.fn(),
};

function renderSheet(initialPath = '/') {
  return render(
    <ThemeProvider defaultTheme="light">
      <ActiveLanguageContext.Provider value={NO_LANGUAGES}>
        <MemoryRouter initialEntries={[initialPath]}>
          <MoreSheet />
        </MemoryRouter>
      </ActiveLanguageContext.Provider>
    </ThemeProvider>,
  );
}

async function openSheet() {
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'More' }));
  return { user, sheet: screen.getByRole('dialog', { name: 'More' }) };
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  document.documentElement.classList.remove('light', 'dark');
});

describe('MoreSheet', () => {
  it('lists the Languages / Settings / Account destinations', async () => {
    renderSheet();
    const { sheet } = await openSheet();
    const rows = within(sheet);
    expect(rows.getByRole('link', { name: 'Languages' })).toHaveAttribute(
      'href',
      '/languages',
    );
    expect(rows.getByRole('link', { name: 'Settings' })).toHaveAttribute(
      'href',
      '/settings',
    );
    expect(rows.getByRole('link', { name: 'Account' })).toHaveAttribute(
      'href',
      '/account',
    );
    // No Sign out row — the header banner owns the single sign-out control.
    expect(rows.queryByRole('button', { name: /sign out/i })).toBeNull();
    expect(rows.queryByRole('link', { name: /sign out/i })).toBeNull();
  });

  it('offers an explicit close control (touch screen readers cannot rely on Escape/overlay)', async () => {
    renderSheet();
    const { user, sheet } = await openSheet();

    await user.click(within(sheet).getByRole('button', { name: 'Close' }));

    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'More' })).toBeNull(),
    );
  });

  it('closes when a destination is tapped', async () => {
    renderSheet();
    const { user } = await openSheet();

    await user.click(screen.getByRole('link', { name: 'Settings' }));

    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'More' })).toBeNull(),
    );
  });

  it('carries a working dark-mode switch', async () => {
    renderSheet();
    const { user, sheet } = await openSheet();

    const toggle = within(sheet).getByRole('switch', { name: 'Dark mode' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');

    await user.click(toggle);
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(toggle).toHaveAttribute('aria-checked', 'true');

    await user.click(toggle);
    expect(document.documentElement.classList.contains('light')).toBe(true);
  });

  it('carries the CEFR panel (unreachable below `sm` otherwise)', async () => {
    renderSheet();
    const { sheet } = await openSheet();
    expect(
      within(sheet).getByRole('region', { name: 'Proficiency level' }),
    ).toBeInTheDocument();
  });

  it('highlights the More slot while a sheet destination is the active route', () => {
    renderSheet('/settings');
    expect(screen.getByRole('button', { name: 'More' })).toHaveClass(
      'text-primary',
    );
  });
});
