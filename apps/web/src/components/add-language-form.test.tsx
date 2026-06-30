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

  type SuccessResult = {
    language: typeof CREATED;
    created: boolean;
    bandError: boolean;
  };

  /** A `mutate` stub that immediately resolves with a given add outcome. */
  function mutateWith(result: SuccessResult) {
    return vi.fn(
      (_input: unknown, opts: { onSuccess: (r: SuccessResult) => void }) => {
        opts.onSuccess(result);
      },
    );
  }

  it('toasts and calls onCreated after a successful add, then resets', async () => {
    const mutate = mutateWith({
      language: CREATED,
      created: true,
      bandError: false,
    });
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

  it('S3: shows a "you already have it" toast on an idempotent re-add (created=false)', async () => {
    const mutate = mutateWith({
      language: CREATED,
      created: false,
      bandError: false,
    });
    useAddLanguage.mockReturnValue({ mutate, isPending: false });
    const onCreated = vi.fn();
    render(<AddLanguageForm onCreated={onCreated} />);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Name'), 'French');
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Already in your languages',
        description: expect.stringContaining('You already have French'),
      }),
    );
    // Not the "added" toast, and the language is still handed back (e.g. to make it active).
    expect(toast).not.toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Language added' }),
    );
    expect(onCreated).toHaveBeenCalledWith(CREATED);
  });

  it('S12: warns (without claiming failure) when the language was created but the level failed', async () => {
    const mutate = mutateWith({
      language: CREATED,
      created: true,
      bandError: true,
    });
    useAddLanguage.mockReturnValue({ mutate, isPending: false });
    const onCreated = vi.fn();
    render(<AddLanguageForm onCreated={onCreated} />);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Name'), 'French');
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({
        variant: 'destructive',
        title: expect.stringContaining('starting level'),
      }),
    );
    // The language WAS created → still handed back, never the hard "could not add" error.
    expect(onCreated).toHaveBeenCalledWith(CREATED);
    expect(toast).not.toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Could not add language' }),
    );
  });

  it('S14: requires a code when vowel marks are on and blocks the submit', async () => {
    const mutate = vi.fn();
    useAddLanguage.mockReturnValue({ mutate, isPending: false });
    render(<AddLanguageForm />);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Name'), 'Hebrew');
    await user.click(screen.getByLabelText(/include vowel marks/i));
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(screen.getByText(/enter a language code/i)).toBeInTheDocument();
    expect(mutate).not.toHaveBeenCalled();
  });

  it('S14: submits a vowelized language once a code is provided', async () => {
    const mutate = vi.fn();
    useAddLanguage.mockReturnValue({ mutate, isPending: false });
    render(<AddLanguageForm />);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Name'), 'Hebrew');
    await user.type(screen.getByLabelText('Code (optional)'), 'he');
    await user.click(screen.getByLabelText(/include vowel marks/i));
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toEqual({
      name: 'Hebrew',
      code: 'he',
      vowelized: true,
      band: 'A1',
    });
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
