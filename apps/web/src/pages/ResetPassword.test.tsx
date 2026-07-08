import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { updatePassword, readAuthRedirectError } = vi.hoisted(() => ({
  updatePassword: vi.fn(),
  readAuthRedirectError: vi.fn(),
}));
vi.mock('@/lib/auth', () => ({ updatePassword, readAuthRedirectError }));

import ResetPassword from '@/pages/ResetPassword';

function renderReset() {
  return render(
    <MemoryRouter>
      <ResetPassword />
    </MemoryRouter>,
  );
}

async function fillNewPassword(password: string, confirm: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('New password'), password);
  await user.type(screen.getByLabelText('Confirm new password'), confirm);
  await user.click(screen.getByRole('button', { name: /update password/i }));
  return user;
}

beforeEach(() => {
  vi.clearAllMocks();
  readAuthRedirectError.mockReturnValue(null);
  updatePassword.mockResolvedValue({ error: null });
});

describe('ResetPassword', () => {
  it('exposes exactly ONE heading (its h1) — the "Lengua" wordmark is not a heading', () => {
    renderReset();
    expect(screen.getAllByRole('heading')).toHaveLength(1);
    expect(
      screen.getByRole('heading', { name: /set a new password/i }),
    ).toBeInTheDocument();
    expect(screen.getByText('Lengua')).toBeInTheDocument();
  });

  it('shows an expired-link state when the redirect carried an error', () => {
    readAuthRedirectError.mockReturnValue({
      code: 'otp_expired',
      description: 'Email link is invalid or has expired',
    });
    renderReset();
    expect(
      screen.getByRole('heading', { name: /link expired/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /request a new reset link/i }),
    ).toHaveAttribute('href', '/forgot-password');
    expect(screen.queryByLabelText('New password')).not.toBeInTheDocument();
  });

  it('falls back to generic copy when the error has no description', () => {
    readAuthRedirectError.mockReturnValue({
      code: 'access_denied',
      description: null,
    });
    renderReset();
    expect(screen.getByText(/invalid or has expired/i)).toBeInTheDocument();
  });

  it('gives both new-password fields a reveal toggle', () => {
    renderReset();
    const password = screen.getByLabelText('New password') as HTMLInputElement;
    const confirm = screen.getByLabelText(
      'Confirm new password',
    ) as HTMLInputElement;
    expect(password).toHaveAttribute('type', 'password');
    expect(confirm).toHaveAttribute('type', 'password');
    const toggles = screen.getAllByRole('button', { name: 'Show password' });
    expect(toggles).toHaveLength(2);

    fireEvent.keyDown(toggles[1], { key: 'Enter' });
    expect(confirm).toHaveAttribute('type', 'text');
    expect(password).toHaveAttribute('type', 'password');
  });

  it('validates that the passwords match', async () => {
    renderReset();
    await fillNewPassword('Abcdef12', 'Mismatch1');
    expect(screen.getByText(/do not match/i)).toBeInTheDocument();
    expect(updatePassword).not.toHaveBeenCalled();
  });

  it('updates the password and shows a success state', async () => {
    renderReset();
    await fillNewPassword('Abcdef12', 'Abcdef12');
    expect(updatePassword).toHaveBeenCalledWith('Abcdef12');
    expect(
      await screen.findByRole('heading', { name: /password updated/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /continue to lengua/i }),
    ).toHaveAttribute('href', '/');
  });

  it('surfaces a server error', async () => {
    updatePassword.mockResolvedValue({
      error: 'Your new password must be different from the old one.',
    });
    renderReset();
    await fillNewPassword('Abcdef12', 'Abcdef12');
    expect(await screen.findByRole('alert')).toHaveTextContent(/different/i);
  });
});
