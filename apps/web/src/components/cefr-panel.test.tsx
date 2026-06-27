import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { useProficiencyQuery, useSetProficiencyBand } = vi.hoisted(() => ({
  useProficiencyQuery: vi.fn(),
  useSetProficiencyBand: vi.fn(),
}));
vi.mock('@/lib/proficiency', () => ({
  useProficiencyQuery,
  useSetProficiencyBand,
  proficiencyKey: (id: number) => ['proficiency', id],
}));

const { toast } = vi.hoisted(() => ({ toast: vi.fn() }));
vi.mock('@/components/ui/use-toast', () => ({ toast }));

import {
  ActiveLanguageContext,
  type ActiveLanguageState,
} from '@/components/active-language-context';
import { CefrPanel } from '@/components/cefr-panel';

const SPANISH = { id: 7, name: 'Spanish', code: 'es', vowelized: false };

function renderPanel(overrides: Partial<ActiveLanguageState> = {}) {
  const value: ActiveLanguageState = {
    languages: [SPANISH],
    activeLanguageId: 7,
    activeLanguage: SPANISH,
    setActiveLanguageId: vi.fn(),
    isLoading: false,
    isError: false,
    ...overrides,
  };
  render(
    <ActiveLanguageContext.Provider value={value}>
      <CefrPanel />
    </ActiveLanguageContext.Provider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useSetProficiencyBand.mockReturnValue({ mutate: vi.fn(), isPending: false });
});

describe('CefrPanel', () => {
  it('prompts to add a language when none is active', () => {
    renderPanel({ activeLanguageId: null, activeLanguage: null });
    expect(
      screen.getByText(/add a language to track your level/i),
    ).toBeInTheDocument();
    expect(useProficiencyQuery).not.toHaveBeenCalled();
  });

  it('shows a loading state while the level loads', () => {
    useProficiencyQuery.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    });
    renderPanel();
    expect(screen.getByText(/loading level/i)).toBeInTheDocument();
  });

  it('shows an error state when the level fails to load', () => {
    useProficiencyQuery.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    });
    renderPanel();
    expect(screen.getByRole('alert')).toHaveTextContent(/couldn.t load/i);
  });

  it('renders the band label and progress percentage', () => {
    useProficiencyQuery.mockReturnValue({
      data: { band: 'B1', progress: 0.4, score: 2.4 },
      isLoading: false,
      isError: false,
    });
    renderPanel();

    // The prominent band label, not the same-named <option> in the override select.
    expect(screen.getByTestId('cefr-band')).toHaveTextContent('B1');
    expect(screen.getByText('40%')).toBeInTheDocument();
    expect(screen.getByText('Progress to B2')).toBeInTheDocument();

    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-valuenow', '40');
    expect(bar).toHaveAttribute('aria-label', 'Progress to B2');

    // The override select reflects the current band.
    const override = screen.getByLabelText(
      'Override level',
    ) as HTMLSelectElement;
    expect(override.value).toBe('B1');
  });

  it('still renders the level when the active language object is not yet resolved', () => {
    useProficiencyQuery.mockReturnValue({
      data: { band: 'A2', progress: 0.2, score: 1.2 },
      isLoading: false,
      isError: false,
    });
    renderPanel({ activeLanguageId: 7, activeLanguage: null });
    expect(screen.getByTestId('cefr-band')).toHaveTextContent('A2');
  });

  it('shows the top-level state at C2 (no next band)', () => {
    useProficiencyQuery.mockReturnValue({
      data: { band: 'C2', progress: 1, score: 6 },
      isLoading: false,
      isError: false,
    });
    renderPanel();
    expect(screen.getByText('Top level (C2)')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute(
      'aria-label',
      'Top level reached',
    );
  });

  it('overriding the band submits the new band', async () => {
    const mutate = vi.fn();
    useSetProficiencyBand.mockReturnValue({ mutate, isPending: false });
    useProficiencyQuery.mockReturnValue({
      data: { band: 'B1', progress: 0.4, score: 2.4 },
      isLoading: false,
      isError: false,
    });
    renderPanel();

    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText('Override level'), 'C1');

    expect(mutate).toHaveBeenCalledWith('C1', expect.any(Object));
  });

  it('toasts when the override fails', async () => {
    const mutate = vi.fn(
      (_band: string, opts: { onError: (e: unknown) => void }) => {
        opts.onError(new Error('boom'));
      },
    );
    useSetProficiencyBand.mockReturnValue({ mutate, isPending: false });
    useProficiencyQuery.mockReturnValue({
      data: { band: 'B1', progress: 0.4, score: 2.4 },
      isLoading: false,
      isError: false,
    });
    renderPanel();

    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText('Override level'), 'C1');

    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({ variant: 'destructive' }),
    );
  });
});
