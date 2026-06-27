import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { useRemoveLanguage } = vi.hoisted(() => ({
  useRemoveLanguage: vi.fn(),
}));
vi.mock('@/lib/languages', () => ({ useRemoveLanguage }));

const { toast } = vi.hoisted(() => ({ toast: vi.fn() }));
vi.mock('@/components/ui/use-toast', () => ({ toast }));

import { ApiError } from '@/lib/api-client';
import { RemoveLanguageDialog } from '@/components/remove-language-dialog';

const FRENCH = { id: 5, name: 'French', code: 'fr', vowelized: false };

beforeEach(() => {
  vi.clearAllMocks();
  useRemoveLanguage.mockReturnValue({ mutate: vi.fn(), isPending: false });
});

describe('RemoveLanguageDialog', () => {
  it('only deletes after the in-dialog confirmation (the trigger alone does not)', async () => {
    const mutate = vi.fn();
    useRemoveLanguage.mockReturnValue({ mutate, isPending: false });
    render(<RemoveLanguageDialog language={FRENCH} />);

    const user = userEvent.setup();
    // Opening the dialog must not delete anything yet.
    await user.click(screen.getByRole('button', { name: 'Remove French' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Remove French?')).toBeInTheDocument();
    expect(
      within(dialog).getByText(/all of its flashcards and your progress/i),
    ).toBeInTheDocument();
    expect(mutate).not.toHaveBeenCalled();

    // Confirming fires the delete.
    await user.click(within(dialog).getByRole('button', { name: 'Remove' }));
    expect(mutate).toHaveBeenCalledWith(5, expect.any(Object));
  });

  it('closes, toasts and calls onRemoved on success', async () => {
    const mutate = vi.fn((_id: number, opts: { onSuccess: () => void }) =>
      opts.onSuccess(),
    );
    useRemoveLanguage.mockReturnValue({ mutate, isPending: false });
    const onRemoved = vi.fn();
    render(<RemoveLanguageDialog language={FRENCH} onRemoved={onRemoved} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Remove French' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Remove' }));

    expect(onRemoved).toHaveBeenCalledWith(FRENCH);
    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Language removed' }),
    );
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    );
  });

  it('toasts an error and stays open on failure', async () => {
    const mutate = vi.fn(
      (_id: number, opts: { onError: (e: unknown) => void }) =>
        opts.onError(new Error('nope')),
    );
    useRemoveLanguage.mockReturnValue({ mutate, isPending: false });
    render(<RemoveLanguageDialog language={FRENCH} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Remove French' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Remove' }));

    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({ variant: 'destructive' }),
    );
  });

  it('surfaces the API error message on a typed failure', async () => {
    const mutate = vi.fn(
      (_id: number, opts: { onError: (e: unknown) => void }) =>
        opts.onError(new ApiError({ status: 409, message: 'Still in use.' })),
    );
    useRemoveLanguage.mockReturnValue({ mutate, isPending: false });
    render(<RemoveLanguageDialog language={FRENCH} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Remove French' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Remove' }));

    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({
        variant: 'destructive',
        description: 'Still in use.',
      }),
    );
  });

  it('shows a pending state while the delete is in flight', async () => {
    useRemoveLanguage.mockReturnValue({ mutate: vi.fn(), isPending: true });
    render(<RemoveLanguageDialog language={FRENCH} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Remove French' }));
    const dialog = await screen.findByRole('dialog');
    expect(
      within(dialog).getByRole('button', { name: /removing/i }),
    ).toBeDisabled();
  });
});
