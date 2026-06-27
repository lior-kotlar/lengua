import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Capture the DELETE transport (keep the real unwrap/ApiError) + stub the auth sign-out.
const { del } = vi.hoisted(() => ({ del: vi.fn() }));
vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, getApiClient: () => ({ DELETE: del }) };
});
const { signOut } = vi.hoisted(() => ({ signOut: vi.fn() }));
vi.mock('@/lib/auth', () => ({ signOut }));

import { DeleteAccountDialog } from '@/components/delete-account-dialog';

const CONFIRM_PHRASE = 'delete my account';

function ok<T>(data: T, status = 200) {
  return Promise.resolve({
    data,
    error: undefined,
    response: new Response(null, { status }),
  });
}

function fail(status: number, detail: string) {
  return Promise.resolve({
    data: undefined,
    error: { detail },
    response: new Response(null, { status }),
  });
}

function renderDialog(
  queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  }),
) {
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/account']}>
        <Routes>
          <Route path="/account" element={<DeleteAccountDialog />} />
          <Route path="/login" element={<div>LOGIN ROUTE</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { queryClient };
}

/** Open the dialog and return its element + the confirm submit button + phrase input. */
async function openDialog(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Delete account' }));
  const dialog = await screen.findByRole('dialog');
  const confirm = within(dialog).getByRole('button', {
    name: 'Delete account',
  });
  const input = within(dialog).getByLabelText(/to confirm/i);
  return { dialog, confirm, input };
}

beforeEach(() => {
  vi.clearAllMocks();
  signOut.mockResolvedValue({ error: null });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('DeleteAccountDialog — confirmation gate', () => {
  it('the trigger only opens the dialog and never deletes', async () => {
    const user = userEvent.setup();
    renderDialog();
    const { confirm } = await openDialog(user);
    expect(del).not.toHaveBeenCalled();
    expect(confirm).toBeDisabled();
  });

  it('keeps the delete button disabled until the EXACT phrase is typed', async () => {
    const user = userEvent.setup();
    renderDialog();
    const { confirm, input } = await openDialog(user);

    await user.type(input, 'delete');
    expect(confirm).toBeDisabled();

    await user.type(input, ' my account!'); // now "delete my account!" — still not exact
    expect(confirm).toBeDisabled();

    await user.clear(input);
    await user.type(input, CONFIRM_PHRASE);
    expect(confirm).toBeEnabled();
  });

  it('does not fire deletion when the form is submitted without the exact phrase', async () => {
    const user = userEvent.setup();
    renderDialog();
    const { dialog, input } = await openDialog(user);

    await user.type(input, 'wrong');
    // Bypass the disabled button and submit the form directly — the handler must still refuse.
    fireEvent.submit(dialog.querySelector('form')!);
    expect(del).not.toHaveBeenCalled();
  });
});

describe('DeleteAccountDialog — confirmed deletion', () => {
  it('calls DELETE once, signs out, clears the cache, and redirects to /login', async () => {
    const user = userEvent.setup();
    del.mockReturnValue(ok(undefined, 204));
    const { queryClient } = renderDialog();
    queryClient.setQueryData(['languages'], [{ id: 1 }]); // some cached data to prove the reset

    const { confirm, input } = await openDialog(user);
    await user.type(input, CONFIRM_PHRASE);
    await user.click(confirm);

    expect(await screen.findByText('LOGIN ROUTE')).toBeInTheDocument();
    expect(del).toHaveBeenCalledTimes(1);
    expect(del).toHaveBeenCalledWith('/account');
    expect(signOut).toHaveBeenCalledTimes(1);
    expect(queryClient.getQueryData(['languages'])).toBeUndefined();
  });

  it('surfaces the retryable 502 friendly, stays open, and does not sign out', async () => {
    const user = userEvent.setup();
    del.mockReturnValue(
      fail(502, 'Account deletion failed; no data was removed. Please retry.'),
    );
    renderDialog();

    const { confirm, input } = await openDialog(user);
    await user.type(input, CONFIRM_PHRASE);
    await user.click(confirm);

    expect(await screen.findByText(/no data was removed/i)).toBeInTheDocument();
    expect(del).toHaveBeenCalledTimes(1);
    expect(signOut).not.toHaveBeenCalled();
    expect(screen.queryByText('LOGIN ROUTE')).not.toBeInTheDocument();
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('shows a pending state and cannot double-submit while a delete is in flight', async () => {
    const user = userEvent.setup();
    // A never-resolving DELETE keeps the mutation pending.
    del.mockReturnValue(new Promise(() => {}));
    renderDialog();

    const { dialog, input } = await openDialog(user);
    await user.type(input, CONFIRM_PHRASE);
    await user.click(
      within(dialog).getByRole('button', { name: 'Delete account' }),
    );

    const pending = within(dialog).getByRole('button', { name: /deleting/i });
    expect(pending).toBeDisabled();
    expect(input).toBeDisabled();

    // A second submit while pending must not fire a second DELETE.
    fireEvent.submit(dialog.querySelector('form')!);
    expect(del).toHaveBeenCalledTimes(1);
  });

  it('resets the typed phrase and any error when the dialog is closed', async () => {
    const user = userEvent.setup();
    del.mockReturnValue(
      fail(502, 'Account deletion failed; no data was removed.'),
    );
    renderDialog();

    let dialog = (await openDialog(user)).dialog;
    const input = within(dialog).getByLabelText(/to confirm/i);
    await user.type(input, CONFIRM_PHRASE);
    await user.click(
      within(dialog).getByRole('button', { name: 'Delete account' }),
    );
    expect(await screen.findByText(/no data was removed/i)).toBeInTheDocument();

    // Close, then reopen — phrase + error are gone and the button is disabled again.
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    );

    dialog = (await openDialog(user)).dialog;
    expect(within(dialog).getByLabelText(/to confirm/i)).toHaveValue('');
    expect(
      within(dialog).queryByText(/no data was removed/i),
    ).not.toBeInTheDocument();
    expect(
      within(dialog).getByRole('button', { name: 'Delete account' }),
    ).toBeDisabled();
  });
});
