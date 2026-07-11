import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { useAddLanguage } = vi.hoisted(() => ({ useAddLanguage: vi.fn() }));
vi.mock('@/lib/languages', () => ({ useAddLanguage }));

const { toast } = vi.hoisted(() => ({ toast: vi.fn() }));
vi.mock('@/components/ui/use-toast', () => ({ toast }));

import { ApiError } from '@/lib/api-client';
import type { LanguageOut } from '@/lib/languages';
import { AddLanguageForm } from '@/components/add-language-form';

const CREATED = { id: 5, name: 'French', code: 'fr', vowelized: false };

beforeEach(() => {
  vi.clearAllMocks();
  useAddLanguage.mockReturnValue({ mutate: vi.fn(), isPending: false });
});

/**
 * Pick a curated language by typing its (search) text into the combobox and clicking its option.
 * The name is anchored at the start so it selects the curated row (e.g. "French Français"), not the
 * custom row ("Add "French" as a custom language…"), which also contains the text.
 */
async function pickCurated(
  user: ReturnType<typeof userEvent.setup>,
  text: string,
) {
  await user.type(screen.getByRole('combobox'), text);
  await user.click(
    screen.getByRole('option', { name: new RegExp(`^${text}`, 'i') }),
  );
}

/** Switch to the custom path with a given search query (empty query = the bare custom row). */
async function goCustom(
  user: ReturnType<typeof userEvent.setup>,
  query: string,
) {
  if (query !== '') {
    await user.type(screen.getByRole('combobox'), query);
  }
  await user.click(screen.getByRole('option', { name: /custom language/i }));
}

describe('AddLanguageForm — picker entry', () => {
  it('shows the searchable combobox first, with no Name/Code inputs', () => {
    render(<AddLanguageForm />);
    expect(screen.getByRole('combobox')).toBeInTheDocument();
    expect(screen.queryByLabelText('Name')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/code/i)).not.toBeInTheDocument();
  });

  it('does NOT steal focus onto the combobox on first render', () => {
    render(<AddLanguageForm />);
    // A picker mounted fresh (page load) must not autofocus — that would grab focus on the page.
    expect(screen.getByRole('combobox')).not.toHaveFocus();
  });
});

describe('AddLanguageForm — focus management on step transitions', () => {
  it('focuses the level select when a curated language is picked', async () => {
    render(<AddLanguageForm />);
    const user = userEvent.setup();
    await pickCurated(user, 'French');
    await waitFor(() =>
      expect(screen.getByLabelText('Starting level')).toHaveFocus(),
    );
  });

  it('focuses the Name field when the custom path opens', async () => {
    render(<AddLanguageForm />);
    const user = userEvent.setup();
    await goCustom(user, 'Klingon');
    await waitFor(() => expect(screen.getByLabelText('Name')).toHaveFocus());
  });

  it('returns focus to the combobox when going back to the picker', async () => {
    render(<AddLanguageForm />);
    const user = userEvent.setup();
    await pickCurated(user, 'French');
    await user.click(screen.getByRole('button', { name: /change/i }));
    await waitFor(() => expect(screen.getByRole('combobox')).toHaveFocus());
  });
});

describe('AddLanguageForm — curated path', () => {
  it('shows no Name/Code inputs and a chip after picking a curated language', async () => {
    render(<AddLanguageForm />);
    const user = userEvent.setup();
    await pickCurated(user, 'French');

    // The chip + level are shown; the free-text Name/Code inputs are NOT.
    expect(screen.getByText('French')).toBeInTheDocument();
    expect(screen.getByText('Français')).toBeInTheDocument();
    expect(screen.getByLabelText('Starting level')).toBeInTheDocument();
    expect(screen.queryByLabelText('Name')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/code/i)).not.toBeInTheDocument();
  });

  it('submits {name, code, vowelized:false, band} for a non-vowelizable curated pick', async () => {
    const mutate = vi.fn();
    useAddLanguage.mockReturnValue({ mutate, isPending: false });
    render(<AddLanguageForm />);

    const user = userEvent.setup();
    await pickCurated(user, 'French');
    await user.selectOptions(screen.getByLabelText('Starting level'), 'B1');
    // A non-vowelizable language never shows the vowel-marks toggle.
    expect(screen.queryByLabelText(/vowel marks/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toEqual({
      name: 'French',
      code: 'fr',
      vowelized: false,
      band: 'B1',
      curated: true,
    });
  });

  it('defaults the vowel-marks toggle ON for a vowelizable curated pick (e.g. Arabic)', async () => {
    const mutate = vi.fn();
    useAddLanguage.mockReturnValue({ mutate, isPending: false });
    render(<AddLanguageForm />);

    const user = userEvent.setup();
    await pickCurated(user, 'Arabic');
    const toggle = screen.getByLabelText(/vowel marks/i) as HTMLInputElement;
    expect(toggle.checked).toBe(true);
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(mutate.mock.calls[0][0]).toEqual({
      name: 'Arabic',
      code: 'ar',
      vowelized: true,
      band: 'A1',
      curated: true,
    });
  });

  it('lets the user untick vowel marks on a vowelizable curated pick', async () => {
    const mutate = vi.fn();
    useAddLanguage.mockReturnValue({ mutate, isPending: false });
    render(<AddLanguageForm />);

    const user = userEvent.setup();
    await pickCurated(user, 'Hebrew');
    await user.click(screen.getByLabelText(/vowel marks/i)); // untick
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(mutate.mock.calls[0][0]).toEqual({
      name: 'Hebrew',
      code: 'he',
      vowelized: false,
      band: 'A1',
      curated: true,
    });
  });

  it('returns to the picker via the Change affordance', async () => {
    render(<AddLanguageForm />);
    const user = userEvent.setup();
    await pickCurated(user, 'French');
    await user.click(screen.getByRole('button', { name: /change/i }));
    // Back on the picker: the combobox is shown and the curated chip's controls are gone.
    expect(screen.getByRole('combobox')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /change/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /add language/i }),
    ).not.toBeInTheDocument();
  });
});

describe('AddLanguageForm — custom (experimental) path', () => {
  it('prefills the name from the query under an experimental heading with the footnote', async () => {
    render(<AddLanguageForm />);
    const user = userEvent.setup();
    await goCustom(user, 'Klingon');

    expect(
      screen.getByRole('heading', { name: /custom \(experimental\)/i }),
    ).toBeInTheDocument();
    expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe(
      'Klingon',
    );
    expect(
      screen.getByText(/sentence quality depends on the ai model/i),
    ).toBeInTheDocument();
  });

  it('submits the trimmed custom fields including the chosen band', async () => {
    const mutate = vi.fn();
    useAddLanguage.mockReturnValue({ mutate, isPending: false });
    render(<AddLanguageForm />);

    const user = userEvent.setup();
    await goCustom(user, 'Esperanto');
    await user.type(screen.getByLabelText('Code (optional)'), 'eo');
    await user.selectOptions(screen.getByLabelText('Starting level'), 'B1');
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toEqual({
      name: 'Esperanto',
      code: 'eo',
      vowelized: false,
      band: 'B1',
      curated: false,
    });
  });

  it('blocks an empty name and shows a validation message', async () => {
    const mutate = vi.fn();
    useAddLanguage.mockReturnValue({ mutate, isPending: false });
    render(<AddLanguageForm />);

    const user = userEvent.setup();
    await goCustom(user, '');
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(screen.getByText(/enter a language name/i)).toBeInTheDocument();
    expect(mutate).not.toHaveBeenCalled();
  });

  it('S14: requires a code when vowel marks are on and blocks the submit', async () => {
    const mutate = vi.fn();
    useAddLanguage.mockReturnValue({ mutate, isPending: false });
    render(<AddLanguageForm />);

    const user = userEvent.setup();
    await goCustom(user, 'Aramaic');
    await user.click(screen.getByLabelText(/vowel marks/i));
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(screen.getByText(/enter a language code/i)).toBeInTheDocument();
    expect(mutate).not.toHaveBeenCalled();
  });

  it('S14: submits a vowelized custom language once a code is provided', async () => {
    const mutate = vi.fn();
    useAddLanguage.mockReturnValue({ mutate, isPending: false });
    render(<AddLanguageForm />);

    const user = userEvent.setup();
    await goCustom(user, 'Aramaic');
    await user.type(screen.getByLabelText(/^code/i), 'arc');
    await user.click(screen.getByLabelText(/vowel marks/i));
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toEqual({
      name: 'Aramaic',
      code: 'arc',
      vowelized: true,
      band: 'A1',
      curated: false,
    });
  });

  it('pre-sets the vowel-marks default when a known code is typed', async () => {
    render(<AddLanguageForm />);
    const user = userEvent.setup();
    await goCustom(user, 'My Arabic');
    const toggle = screen.getByLabelText(/vowel marks/i) as HTMLInputElement;
    expect(toggle.checked).toBe(false);

    // "ar" is a curated vowelizable code → the toggle flips ON (until the user overrides it).
    await user.type(screen.getByLabelText('Code (optional)'), 'ar');
    expect(
      (screen.getByLabelText(/vowel marks/i) as HTMLInputElement).checked,
    ).toBe(true);
    expect(screen.getByText(/recognized as/i)).toHaveTextContent('Arabic');
  });

  it('respects a manual vowel-marks choice over a later code lookup', async () => {
    render(<AddLanguageForm />);
    const user = userEvent.setup();
    await goCustom(user, 'Aramaic');
    // User explicitly ticks vowel marks (needs a code) …
    await user.click(screen.getByLabelText(/vowel marks/i));
    await user.type(screen.getByLabelText('Code'), 'ar'); // curated vowelizable
    // … the tick is preserved (not clobbered by the lookup), and stays on.
    expect(
      (screen.getByLabelText(/vowel marks/i) as HTMLInputElement).checked,
    ).toBe(true);
  });

  it('shows a soft, non-blocking duplicate hint when the code subtag is already used', async () => {
    const mutate = vi.fn();
    useAddLanguage.mockReturnValue({ mutate, isPending: false });
    const existing: LanguageOut[] = [
      { id: 1, name: 'Spanish', code: 'es', vowelized: false },
    ];
    render(<AddLanguageForm existingLanguages={existing} />);

    const user = userEvent.setup();
    await goCustom(user, 'Castilian');
    await user.type(screen.getByLabelText('Code (optional)'), 'es-MX');

    expect(screen.getByRole('status')).toHaveTextContent(/already have/i);
    expect(screen.getByRole('status')).toHaveTextContent('Spanish');
    // The hint does NOT block submission.
    await user.click(screen.getByRole('button', { name: /add language/i }));
    expect(mutate).toHaveBeenCalledTimes(1);
  });

  it('returns to the picker via the back affordance', async () => {
    render(<AddLanguageForm />);
    const user = userEvent.setup();
    await goCustom(user, 'Klingon');
    await user.click(screen.getByRole('button', { name: /back to list/i }));
    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });
});

describe('AddLanguageForm — success/error handling (shared)', () => {
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

  it('toasts, calls onCreated and returns to the picker after a successful add', async () => {
    const mutate = mutateWith({
      language: CREATED,
      created: true,
      bandError: false,
    });
    useAddLanguage.mockReturnValue({ mutate, isPending: false });
    const onCreated = vi.fn();
    render(<AddLanguageForm onCreated={onCreated} />);

    const user = userEvent.setup();
    await pickCurated(user, 'French');
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(onCreated).toHaveBeenCalledWith(CREATED);
    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Language added' }),
    );
    // Reset back to the picker.
    expect(screen.getByRole('combobox')).toBeInTheDocument();
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
    await pickCurated(user, 'French');
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Already in your languages',
        description: expect.stringContaining('You already have French'),
      }),
    );
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
    await pickCurated(user, 'French');
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({
        variant: 'destructive',
        title: expect.stringContaining('starting level'),
      }),
    );
    expect(onCreated).toHaveBeenCalledWith(CREATED);
    expect(toast).not.toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Could not add language' }),
    );
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
    await pickCurated(user, 'French');
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
    await pickCurated(user, 'French');
    await user.click(screen.getByRole('button', { name: /add language/i }));

    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({
        variant: 'destructive',
        description: 'That language already exists.',
      }),
    );
  });

  it('disables the submit button while the add is in flight', async () => {
    useAddLanguage.mockReturnValue({ mutate: vi.fn(), isPending: true });
    render(<AddLanguageForm />);
    const user = userEvent.setup();
    await pickCurated(user, 'French');
    expect(screen.getByRole('button', { name: /adding/i })).toBeDisabled();
  });

  it('#151: locks the curated "Change" affordance while the add is in flight', async () => {
    // isPending must be true BEFORE the pick so the curated step renders in its pending state.
    useAddLanguage.mockReturnValue({ mutate: vi.fn(), isPending: true });
    render(<AddLanguageForm />);
    const user = userEvent.setup();
    await pickCurated(user, 'French');
    // The user cannot navigate back to the picker between pressing "Add" and the success reset.
    expect(screen.getByRole('button', { name: /change/i })).toBeDisabled();
  });

  it('#151: locks the custom "Back to list" affordance while the add is in flight', async () => {
    useAddLanguage.mockReturnValue({ mutate: vi.fn(), isPending: true });
    render(<AddLanguageForm />);
    const user = userEvent.setup();
    await goCustom(user, 'Klingon');
    expect(
      screen.getByRole('button', { name: /back to list/i }),
    ).toBeDisabled();
  });
});
