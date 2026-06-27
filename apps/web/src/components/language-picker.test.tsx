import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import {
  ActiveLanguageContext,
  type ActiveLanguageState,
} from '@/components/active-language-context';
import { LanguagePicker } from '@/components/language-picker';

const LANGS = [
  { id: 1, name: 'Spanish', code: 'es', vowelized: false },
  { id: 2, name: 'French', code: 'fr', vowelized: false },
];

function renderPicker(overrides: Partial<ActiveLanguageState> = {}) {
  const setActiveLanguageId = vi.fn();
  const value: ActiveLanguageState = {
    languages: LANGS,
    activeLanguageId: 1,
    activeLanguage: LANGS[0],
    setActiveLanguageId,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    ...overrides,
  };
  render(
    <MemoryRouter>
      <ActiveLanguageContext.Provider value={value}>
        <LanguagePicker />
      </ActiveLanguageContext.Provider>
    </MemoryRouter>,
  );
  return { setActiveLanguageId };
}

describe('LanguagePicker', () => {
  it('lists the user languages with the active one selected', () => {
    renderPicker();
    const select = screen.getByLabelText(
      'Active language',
    ) as HTMLSelectElement;
    expect(select.value).toBe('1');
    expect(screen.getByRole('option', { name: 'Spanish' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'French' })).toBeInTheDocument();
  });

  it('selecting a language updates the active selection', async () => {
    const user = userEvent.setup();
    const { setActiveLanguageId } = renderPicker();

    await user.selectOptions(screen.getByLabelText('Active language'), '2');

    expect(setActiveLanguageId).toHaveBeenCalledWith(2);
  });

  it('shows an add-language link when the account has no languages', () => {
    renderPicker({
      languages: [],
      activeLanguageId: null,
      activeLanguage: null,
    });
    expect(
      screen.getByRole('link', { name: /add a language/i }),
    ).toHaveAttribute('href', '/languages');
    expect(screen.queryByLabelText('Active language')).not.toBeInTheDocument();
  });

  it('renders the select without crashing when the active id is not yet resolved', () => {
    // Transient window after languages load but before reconciliation picks one: the controlled
    // value falls back to '' (no "uncontrolled→controlled" warning) and the options still render.
    renderPicker({ activeLanguageId: null, activeLanguage: null });
    expect(screen.getByLabelText('Active language')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Spanish' })).toBeInTheDocument();
  });

  it('shows a loading state before the languages arrive', () => {
    renderPicker({
      languages: [],
      activeLanguageId: null,
      activeLanguage: null,
      isLoading: true,
    });
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });
});
