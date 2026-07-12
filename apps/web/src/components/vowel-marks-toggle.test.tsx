import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  ActiveLanguageContext,
  type ActiveLanguageState,
} from '@/components/active-language-context';
import { VOWEL_MARKS_STORAGE_KEY } from '@/components/vowel-marks-context';
import { VowelMarksProvider } from '@/components/vowel-marks-provider';
import { VowelMarksToggle } from '@/components/vowel-marks-toggle';
import type { LanguageOut } from '@/lib/languages';

const HEBREW: LanguageOut = {
  id: 3,
  name: 'Hebrew',
  code: 'he',
  vowelized: true,
};
const ARABIC: LanguageOut = {
  id: 4,
  name: 'Arabic',
  code: 'ar',
  vowelized: true,
};
const SPANISH: LanguageOut = {
  id: 1,
  name: 'Spanish',
  code: 'es',
  vowelized: false,
};

function activeValue(language: LanguageOut | null): ActiveLanguageState {
  return {
    languages: language === null ? [] : [language],
    activeLanguageId: language?.id ?? null,
    activeLanguage: language,
    setActiveLanguageId: vi.fn(),
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  };
}

function renderToggle(language: LanguageOut | null) {
  return render(
    <ActiveLanguageContext.Provider value={activeValue(language)}>
      <VowelMarksProvider>
        <VowelMarksToggle />
      </VowelMarksProvider>
    </ActiveLanguageContext.Provider>,
  );
}

afterEach(() => {
  localStorage.clear();
});

describe('VowelMarksToggle', () => {
  it('is not rendered when there is no active language', () => {
    renderToggle(null);
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
  });

  it('is not rendered for a non-vowelized language', () => {
    renderToggle(SPANISH);
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
  });

  it('renders for a vowelized language and toggles + persists the preference', async () => {
    const user = userEvent.setup();
    renderToggle(HEBREW);

    const toggle = screen.getByRole('switch');
    // Default: marks shown.
    expect(toggle).toHaveAttribute('aria-checked', 'true');

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    expect(localStorage.getItem(VOWEL_MARKS_STORAGE_KEY)).toBe('false');

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    expect(localStorage.getItem(VOWEL_MARKS_STORAGE_KEY)).toBe('true');
  });

  it('labels the toggle with the script-specific term (nikkud for Hebrew)', () => {
    renderToggle(HEBREW);
    expect(screen.getByText('Vowel marks (nikkud)')).toBeInTheDocument();
  });

  it('labels the toggle with the script-specific term (harakat for Arabic)', () => {
    renderToggle(ARABIC);
    expect(screen.getByText('Vowel marks (harakat)')).toBeInTheDocument();
  });

  // WCAG 2.5.3 "Label in Name": the switch's accessible name must CONTAIN its visible label, so a
  // speech-input user who says the visible text can activate it. PR #158 made the visible label
  // language-aware but left a hardcoded aria-label ("Show vowel marks") that no longer matched.
  it('accessible name contains the visible label (nikkud for Hebrew)', () => {
    renderToggle(HEBREW);
    const visibleLabel = 'Vowel marks (nikkud)';
    expect(screen.getByText(visibleLabel)).toBeInTheDocument();
    const toggle = screen.getByRole('switch');
    expect(toggle).toHaveAccessibleName(expect.stringContaining(visibleLabel));
  });

  it('accessible name contains the visible label (harakat for Arabic)', () => {
    renderToggle(ARABIC);
    const visibleLabel = 'Vowel marks (harakat)';
    expect(screen.getByText(visibleLabel)).toBeInTheDocument();
    const toggle = screen.getByRole('switch');
    expect(toggle).toHaveAccessibleName(expect.stringContaining(visibleLabel));
  });

  it('offers a help affordance explaining what vowel marks are', async () => {
    const user = userEvent.setup();
    renderToggle(HEBREW);

    const help = screen.getByRole('button', { name: /about vowel marks/i });
    await user.click(help);
    expect(
      screen.getByText(/optional pronunciation guides/i),
    ).toBeInTheDocument();
  });
});
