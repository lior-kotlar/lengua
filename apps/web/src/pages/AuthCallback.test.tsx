import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
const { readAuthRedirectError, resendVerificationEmail } = vi.hoisted(() => ({
  readAuthRedirectError: vi.fn(),
  resendVerificationEmail: vi.fn(),
}));
vi.mock('@/components/auth-context', () => ({ useAuth }));
vi.mock('@/lib/auth', () => ({
  readAuthRedirectError,
  resendVerificationEmail,
}));

import AuthCallback from '@/pages/AuthCallback';

function renderCallback() {
  return render(
    <MemoryRouter initialEntries={['/auth/callback']}>
      <Routes>
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route path="/" element={<div>Home screen</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  readAuthRedirectError.mockReturnValue(null);
  resendVerificationEmail.mockResolvedValue({ error: null });
});

describe('AuthCallback', () => {
  it('redirects into the app when a session is established', () => {
    useAuth.mockReturnValue({ session: {}, user: {}, loading: false });
    renderCallback();
    expect(screen.getByText('Home screen')).toBeInTheDocument();
  });

  it('shows a verifying state while the token is being consumed', () => {
    useAuth.mockReturnValue({ session: null, user: null, loading: true });
    renderCallback();
    expect(
      screen.getByRole('status', { name: 'Verifying' }),
    ).toBeInTheDocument();
  });

  it('shows the resend CTA when the verification link errored', async () => {
    useAuth.mockReturnValue({ session: null, user: null, loading: false });
    readAuthRedirectError.mockReturnValue({
      code: 'otp_expired',
      description: 'Email link is invalid or has expired',
    });
    renderCallback();

    expect(
      screen.getByRole('heading', { name: /verification failed/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Email link is invalid or has expired'),
    ).toBeInTheDocument();

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Email'), 'demo@lengua.test');
    await user.click(
      screen.getByRole('button', { name: /resend verification email/i }),
    );

    expect(resendVerificationEmail).toHaveBeenCalledWith('demo@lengua.test');
    expect(await screen.findByText(/verification email sent/i)).toBeVisible();
  });

  it('treats no-session/no-error as a failure with a resend CTA', () => {
    useAuth.mockReturnValue({ session: null, user: null, loading: false });
    renderCallback();
    expect(
      screen.getByRole('heading', { name: /verification failed/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /resend verification email/i }),
    ).toBeInTheDocument();
  });

  it('shows an error when the resend fails', async () => {
    useAuth.mockReturnValue({ session: null, user: null, loading: false });
    resendVerificationEmail.mockResolvedValue({ error: 'rate limited' });
    const user = userEvent.setup();
    renderCallback();

    await user.type(screen.getByLabelText('Email'), 'demo@lengua.test');
    await user.click(
      screen.getByRole('button', { name: /resend verification email/i }),
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /could not resend/i,
    );
  });

  it('validates the email before resending', async () => {
    useAuth.mockReturnValue({ session: null, user: null, loading: false });
    const user = userEvent.setup();
    renderCallback();
    await user.click(
      screen.getByRole('button', { name: /resend verification email/i }),
    );
    // Exact match to avoid colliding with the "Enter your email to get a new link" body copy.
    expect(screen.getByText('Enter your email address.')).toBeInTheDocument();
    expect(resendVerificationEmail).not.toHaveBeenCalled();
  });
});
