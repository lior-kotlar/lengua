import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock the transport (POST /account/deletion-request | -confirm) — keep the real unwrap/ApiError.
const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, getApiClient: () => ({ POST: post }) };
});

import DeleteAccount from '@/pages/DeleteAccount';

function ok(data: unknown, status = 200) {
  return Promise.resolve({
    data,
    error: undefined,
    response: new Response(null, { status }),
  });
}

function fail(status: number, detail = 'boom') {
  return Promise.resolve({
    data: undefined,
    error: { detail },
    response: new Response(null, { status }),
  });
}

function renderAt(path: string) {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <DeleteAccount />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe('DeleteAccount — request form (no token)', () => {
  it('POSTs the email and shows the generic acknowledgement', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(
      ok({ status: 'ok', message: 'If an account exists, we sent a link.' }),
    );
    renderAt('/delete-account');

    await user.type(
      screen.getByLabelText(/account email/i),
      'user@example.com',
    );
    await user.click(
      screen.getByRole('button', { name: /request account deletion/i }),
    );

    await waitFor(() =>
      expect(
        screen.getByText(/if an account exists, we sent a link\./i),
      ).toBeInTheDocument(),
    );
    expect(post).toHaveBeenCalledWith('/account/deletion-request', {
      body: { email: 'user@example.com' },
    });
  });

  it('surfaces a rate-limit error without deleting anything', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(
      fail(429, 'Too many deletion requests for this email.'),
    );
    renderAt('/delete-account');

    await user.type(
      screen.getByLabelText(/account email/i),
      'spammed@example.com',
    );
    await user.click(
      screen.getByRole('button', { name: /request account deletion/i }),
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /too many deletion requests/i,
    );
  });

  it('keeps the submit button disabled until an email is entered', () => {
    renderAt('/delete-account');
    expect(
      screen.getByRole('button', { name: /request account deletion/i }),
    ).toBeDisabled();
  });
});

describe('DeleteAccount — confirm (token from the emailed link)', () => {
  it('POSTs the token and shows the deletion-confirmed message', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(
      ok({
        status: 'ok',
        message: 'Your account has been permanently deleted.',
      }),
    );
    renderAt('/delete-account?token=abc.def');

    await user.click(
      screen.getByRole('button', { name: /delete my account permanently/i }),
    );

    await waitFor(() =>
      expect(screen.getByText(/permanently deleted/i)).toBeInTheDocument(),
    );
    expect(post).toHaveBeenCalledWith('/account/deletion-confirm', {
      body: { token: 'abc.def' },
    });
  });

  it('shows an error for an invalid or expired link', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(
      fail(400, 'This deletion link is invalid or has expired.'),
    );
    renderAt('/delete-account?token=stale');

    await user.click(
      screen.getByRole('button', { name: /delete my account permanently/i }),
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /invalid or has expired/i,
    );
  });
});
