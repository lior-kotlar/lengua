import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ActiveLanguageContext,
  type ActiveLanguageState,
} from '@/components/active-language-context';
import { MobileTabBar } from '@/components/mobile-tab-bar';
import { ThemeProvider } from '@/components/theme-provider';

// The More sheet mounts the CefrPanel; a no-language state keeps it off the proficiency query.
const NO_LANGUAGES: ActiveLanguageState = {
  languages: [],
  activeLanguageId: null,
  activeLanguage: null,
  setActiveLanguageId: vi.fn(),
  isLoading: false,
  isError: false,
  refetch: vi.fn(),
};

function renderBar(initialPath = '/') {
  return render(
    <ThemeProvider defaultTheme="light">
      <ActiveLanguageContext.Provider value={NO_LANGUAGES}>
        <MemoryRouter initialEntries={[initialPath]}>
          <MobileTabBar />
        </MemoryRouter>
      </ActiveLanguageContext.Provider>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('MobileTabBar', () => {
  it('renders the four core-loop tabs with their routes', () => {
    renderBar();
    const bar = within(screen.getByTestId('nav-mobile'));
    expect(bar.getByRole('link', { name: 'Dashboard' })).toHaveAttribute(
      'href',
      '/',
    );
    expect(bar.getByRole('link', { name: 'Generate' })).toHaveAttribute(
      'href',
      '/generate',
    );
    expect(bar.getByRole('link', { name: 'Review' })).toHaveAttribute(
      'href',
      '/review',
    );
    expect(bar.getByRole('link', { name: 'Discover' })).toHaveAttribute(
      'href',
      '/discover',
    );
  });

  it('marks only the active tab with aria-current', () => {
    renderBar('/generate');
    const bar = within(screen.getByTestId('nav-mobile'));
    expect(bar.getByRole('link', { name: 'Generate' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    // `end` on "/" keeps Dashboard from matching every route.
    expect(bar.getByRole('link', { name: 'Dashboard' })).not.toHaveAttribute(
      'aria-current',
    );
  });

  it('opens the More sheet from the fifth slot', async () => {
    const user = userEvent.setup();
    renderBar();

    const more = screen.getByRole('button', { name: 'More' });
    expect(more).toHaveAttribute('aria-haspopup', 'dialog');

    await user.click(more);
    const sheet = screen.getByRole('dialog', { name: 'More' });
    expect(
      within(sheet).getByRole('link', { name: 'Languages' }),
    ).toBeInTheDocument();
  });
});
