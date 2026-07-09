import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LanguageCombobox } from '@/components/language-combobox';
import { CURATED_LANGUAGES } from '@/lib/curated-languages';

function setup() {
  const onSelect = vi.fn();
  const onSelectCustom = vi.fn();
  render(
    <LanguageCombobox onSelect={onSelect} onSelectCustom={onSelectCustom} />,
  );
  const input = screen.getByRole('combobox');
  return { onSelect, onSelectCustom, input, user: userEvent.setup() };
}

/** The currently-highlighted option (aria-selected), resolved via aria-activedescendant. */
function activeOption(input: HTMLElement): HTMLElement {
  const id = input.getAttribute('aria-activedescendant');
  expect(id).toBeTruthy();
  const el = document.getElementById(id as string);
  expect(el).not.toBeNull();
  return el as HTMLElement;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('LanguageCombobox', () => {
  it('renders the full curated list plus a custom row on an empty query', () => {
    setup();
    const options = screen.getAllByRole('option');
    // One row per curated language + the always-present custom row.
    expect(options).toHaveLength(CURATED_LANGUAGES.length + 1);
    expect(screen.getByText('Spanish')).toBeInTheDocument();
    expect(screen.getByText('Español')).toBeInTheDocument();
    expect(screen.getByText(/add a custom language/i)).toBeInTheDocument();
  });

  it('wires the combobox ARIA attributes', () => {
    const { input } = setup();
    expect(input).toHaveAttribute('aria-expanded', 'true');
    const listboxId = input.getAttribute('aria-controls');
    expect(listboxId).toBeTruthy();
    expect(screen.getByRole('listbox').id).toBe(listboxId);
    // The first option is the initial active descendant, and its id resolves to a real option.
    expect(input).toHaveAttribute('aria-activedescendant');
    expect(activeOption(input)).toHaveTextContent('Arabic');
  });

  it('keys option ids by language code, so aria-activedescendant tracks the highlighted row', async () => {
    const { input, user } = setup();
    // Arabic is first: its option id is code-keyed (…-option-ar), not positional (…-option-0).
    expect(input.getAttribute('aria-activedescendant')).toMatch(/-option-ar$/);
    // Narrowing to a single match re-targets the active descendant to THAT language's stable id,
    // so a screen reader announces the newly-highlighted row (a positional id would not change).
    await user.type(input, 'Spanish');
    expect(input.getAttribute('aria-activedescendant')).toMatch(/-option-es$/);
    expect(activeOption(input)).toHaveTextContent('Spanish');
  });

  it('filters case-insensitively by English name', async () => {
    const { input, user } = setup();
    await user.type(input, 'span');
    const options = screen.getAllByRole('option');
    // Spanish + the custom row only.
    expect(options).toHaveLength(2);
    expect(screen.getByText('Spanish')).toBeInTheDocument();
    expect(screen.queryByText('French')).not.toBeInTheDocument();
  });

  it('filters by endonym (native name)', async () => {
    const { input, user } = setup();
    await user.type(input, 'עברית');
    expect(screen.getByText('Hebrew')).toBeInTheDocument();
    expect(screen.getAllByRole('option')).toHaveLength(2);
  });

  it('filters by code', async () => {
    const { input, user } = setup();
    await user.type(input, 'ar');
    // "ar" is a substring of several codes / names (Arabic, Hungarian "Magyar" endonym, etc.),
    // but Arabic must be present and French must not.
    expect(screen.getByText('Arabic')).toBeInTheDocument();
    expect(screen.queryByText('French')).not.toBeInTheDocument();
  });

  it('shows ONLY the custom row (with the query) when nothing matches', async () => {
    const { input, user } = setup();
    await user.type(input, 'Klingon');
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(1);
    expect(
      screen.getByText(/add “klingon” as a custom language/i),
    ).toBeInTheDocument();
  });

  it('selects a curated language on click', async () => {
    const { input, user, onSelect, onSelectCustom } = setup();
    await user.type(input, 'French');
    // Anchor at the start so this is the curated row, not the "Add "French" as a custom…" row.
    await user.click(screen.getByRole('option', { name: /^French/ }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0]).toMatchObject({
      name: 'French',
      code: 'fr',
    });
    expect(onSelectCustom).not.toHaveBeenCalled();
  });

  it('selects the custom row on click, passing the trimmed query', async () => {
    const { input, user, onSelectCustom, onSelect } = setup();
    await user.type(input, '  Klingon  ');
    await user.click(screen.getByRole('option', { name: /custom language/i }));
    expect(onSelectCustom).toHaveBeenCalledWith('Klingon');
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('moves the active option with ArrowDown/ArrowUp and wraps around', async () => {
    const { input, user } = setup();
    input.focus();
    // First option active initially.
    expect(activeOption(input)).toHaveTextContent('Arabic');
    await user.keyboard('{ArrowDown}');
    expect(activeOption(input)).toHaveTextContent('Bengali');
    await user.keyboard('{ArrowUp}');
    expect(activeOption(input)).toHaveTextContent('Arabic');
    // ArrowUp from the first row wraps to the last (the custom) row.
    await user.keyboard('{ArrowUp}');
    expect(activeOption(input)).toHaveTextContent(/custom language/i);
  });

  it('selects the active option on Enter', async () => {
    const { input, user, onSelect } = setup();
    input.focus();
    await user.keyboard('{ArrowDown}{Enter}'); // Bengali (second curated row)
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0]).toMatchObject({ name: 'Bengali' });
  });

  it('picks the custom row via Enter when the query matches nothing', async () => {
    const { input, user, onSelectCustom } = setup();
    await user.type(input, 'Klingon');
    await user.keyboard('{Enter}');
    expect(onSelectCustom).toHaveBeenCalledWith('Klingon');
  });

  it('clears the query on Escape', async () => {
    const { input, user } = setup();
    await user.type(input, 'span');
    expect(input).toHaveValue('span');
    await user.keyboard('{Escape}');
    expect(input).toHaveValue('');
    expect(screen.getAllByRole('option')).toHaveLength(
      CURATED_LANGUAGES.length + 1,
    );
  });

  it('ignores Enter/Arrow keys while an IME composition is in progress', () => {
    const { input, onSelect, onSelectCustom } = setup();
    // Simulate a mid-composition query (e.g. typing an endonym via a CJK IME) that matches nothing,
    // so the custom row is active. The composition-commit Enter must NOT select it.
    fireEvent.change(input, { target: { value: 'にほ' } });
    fireEvent.keyDown(input, { key: 'Enter', isComposing: true });
    expect(onSelectCustom).not.toHaveBeenCalled();
    expect(onSelect).not.toHaveBeenCalled();

    // Arrow keys during composition must not move the option highlight either.
    const before = input.getAttribute('aria-activedescendant');
    fireEvent.keyDown(input, { key: 'ArrowDown', isComposing: true });
    expect(input.getAttribute('aria-activedescendant')).toBe(before);

    // Once composition ends, Enter selects normally (custom row, since the query matches nothing).
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onSelectCustom).toHaveBeenCalledWith('にほ');
  });

  it('keeps the highlight in range as filtering narrows the list', async () => {
    const { input, user } = setup();
    input.focus();
    // Highlight a row far down the list…
    for (let i = 0; i < 20; i += 1) {
      await user.keyboard('{ArrowDown}');
    }
    // …then narrow to a single match; the active descendant must still resolve to a real option,
    // and Enter must select that language rather than pointing at a now-missing row.
    await user.type(input, 'Spanish');
    expect(activeOption(input)).toHaveTextContent('Spanish');
  });

  it('renders each endonym in a language-tagged element for script fonts', () => {
    setup();
    const spanish = screen.getByText('Español');
    expect(spanish).toHaveAttribute('lang', 'es');
    const arabic = screen.getByText('العربية');
    expect(arabic).toHaveAttribute('lang', 'ar');
    // Arabic-script endonym gets the Arabic font utility class.
    expect(arabic.className).toContain('font-arabic');
  });
});
