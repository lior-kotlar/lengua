import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { useAddLanguage } = vi.hoisted(() => ({ useAddLanguage: vi.fn() }));
vi.mock('@/lib/languages', () => ({ useAddLanguage }));

const { toast } = vi.hoisted(() => ({ toast: vi.fn() }));
vi.mock('@/components/ui/use-toast', () => ({ toast }));

import { ApiError } from '@/lib/api-client';
import { AddLanguageForm } from '@/components/add-language-form';

const CREATED = { id: 5, name: 'French', code: 'fr', vowelized: false };

beforeEach(() => {
  vi.clearAllMocks();
  useAddLanguage.mockReturnValue({ mutate: vi.fn(), isPending: false });
});

describe('AddLanguageForm', () => {
  it('blocks an empty submit and shows a validation message', async () => {
    const mutate = vi.fn();
    useAddLanguage.mockReturnValue({ mutate, isPending: false });
    render(<AddLanguageForm />);

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(screen.getByText(/enter a language name/i)).toBeInTheDocument();
    expect(mutate).not.toHaveBeenCalled();
  });

  it('submits the trimmed fields including the chosen starting band', async () => {
    const mutate = vi.fn();
    useAddLanguage.mockReturnValue({ mutate, isPending: false });
    render(<AddLanguageForm />);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Name'), '  French  ');
    await user.type(screen.getByLabelText('Code (optional)'), 'fr');
    await user.selectOptions(screen.getByLabelText('Starting level'), 'B1');
    await user.click(screen.getByLabelText(/include vowel marks/i));
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toEqual({
      name: 'French',
      code: 'fr',
      vowelized: true,
      band: 'B1',
    });
  });

  it('toasts and calls onCreated after a successful add, then resets', async () => {
    const mutate = vi.fn(
      (
        _input: unknown,
        opts: { onSuccess: (language: typeof CREATED) => void },
      ) => {
        opts.onSuccess(CREATED);
      },
    );
    useAddLanguage.mockReturnValue({ mutate, isPending: false });
    const onCreated = vi.fn();
    render(<AddLanguageForm onCreated={onCreated} />);

    const user = userEvent.setup();
    const nameInput = screen.getByLabelText('Name') as HTMLInputElement;
    await user.type(nameInput, 'French');
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(onCreated).toHaveBeenCalledWith(CREATED);
    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Language added' }),
    );
    // Form reset on success.
    expect(nameInput.value).toBe('');
  });

  it('toasts an error when the add fails', async () => {
    const mutate = vi.fn(
      (_input: unknown, opts: { onError: (e: unknown) => void }) => {
        opts.onError(new Error('nope'));
      },
    );
    useAddLanguage.mockReturnValue({ mutate, isPending: false });
    render(<AddLanguageForm />);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Name'), 'French');
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({ variant: 'destructive' }),
    );
  });

  it('surfaces the API error message when the add fails with an ApiError', async () => {
    const mutate = vi.fn(
      (_input: unknown, opts: { onError: (e: unknown) => void }) => {
        opts.onError(
          new ApiError({
            status: 422,
            message: 'That language already exists.',
          }),
        );
      },
    );
    useAddLanguage.mockReturnValue({ mutate, isPending: false });
    render(<AddLanguageForm />);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Name'), 'Spanish');
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({
        variant: 'destructive',
        description: 'That language already exists.',
      }),
    );
  });

  it('disables the submit button while the add is in flight', () => {
    useAddLanguage.mockReturnValue({ mutate: vi.fn(), isPending: true });
    render(<AddLanguageForm />);
    expect(screen.getByRole('button', { name: /adding/i })).toBeDisabled();
  });
});
