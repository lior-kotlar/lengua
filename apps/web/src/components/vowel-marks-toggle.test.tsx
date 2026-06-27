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

    const toggle = screen.getByRole('switch', { name: 'Show vowel marks' });
    // Default: marks shown.
    expect(toggle).toHaveAttribute('aria-checked', 'true');

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    expect(localStorage.getItem(VOWEL_MARKS_STORAGE_KEY)).toBe('false');

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    expect(localStorage.getItem(VOWEL_MARKS_STORAGE_KEY)).toBe('true');
  });
});
