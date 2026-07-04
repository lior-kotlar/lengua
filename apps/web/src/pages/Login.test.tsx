import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { signInWithEmail, resendVerificationEmail } = vi.hoisted(() => ({
  signInWithEmail: vi.fn(),
  resendVerificationEmail: vi.fn(),
}));
vi.mock('@/lib/auth', () => ({ signInWithEmail, resendVerificationEmail }));
vi.mock('@/components/oauth-buttons', () => ({
  OAuthButtons: () => <div data-testid="oauth-buttons" />,
}));

import Login from '@/pages/Login';

function renderLogin() {
  return render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>,
  );
}

async function fillAndSubmit(
  email = 'demo@lengua.test',
  password = 'Abcdef12',
) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Email'), email);
  await user.type(screen.getByLabelText('Password'), password);
  await user.click(screen.getByRole('button', { name: 'Log in' }));
  return user;
}

beforeEach(() => {
  vi.clearAllMocks();
  signInWithEmail.mockResolvedValue({ error: null });
  resendVerificationEmail.mockResolvedValue({ error: null });
});

describe('Login', () => {
  it('renders the heading, forgot-password link and OAuth buttons', () => {
    renderLogin();
    expect(
      screen.getByRole('heading', { name: /log in/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /forgot password/i }),
    ).toHaveAttribute('href', '/forgot-password');
    expect(screen.getByTestId('oauth-buttons')).toBeInTheDocument();
  });

  it('exposes exactly ONE heading (its h1) — the "Lengua" wordmark is not a heading', () => {
    // The staging navigateTo/auth specs match headings by case-insensitive substring, so any second
    // heading (wordmark/eyebrow) would collide with the /log in/i lookup — it must stay a <p>.
    renderLogin();
    expect(screen.getAllByRole('heading')).toHaveLength(1);
    expect(screen.getByText('Lengua')).toBeInTheDocument();
  });

  it('submits credentials to signInWithEmail', async () => {
    renderLogin();
    await fillAndSubmit();
    expect(signInWithEmail).toHaveBeenCalledWith(
      'demo@lengua.test',
      'Abcdef12',
    );
  });

  it('shows a bad-credentials error', async () => {
    signInWithEmail.mockResolvedValue({
      error: 'Incorrect email or password.',
      code: 'invalid_credentials',
    });
    renderLogin();
    await fillAndSubmit();
    expect(
      await screen.findByText('Incorrect email or password.'),
    ).toBeVisible();
    // Not the unverified path → no resend CTA.
    expect(
      screen.queryByRole('button', { name: /resend verification/i }),
    ).not.toBeInTheDocument();
  });

  it('offers a resend action for an unverified email', async () => {
    signInWithEmail.mockResolvedValue({
      error: 'Please verify your email address before signing in.',
      code: 'email_not_confirmed',
    });
    renderLogin();
    const user = await fillAndSubmit();

    const resend = await screen.findByRole('button', {
      name: /resend verification/i,
    });
    await user.click(resend);

    expect(resendVerificationEmail).toHaveBeenCalledWith('demo@lengua.test');
    expect(await screen.findByText(/verification email sent/i)).toBeVisible();
  });

  it('shows an error when the resend fails', async () => {
    signInWithEmail.mockResolvedValue({
      error: 'Please verify your email address before signing in.',
      code: 'email_not_confirmed',
    });
    resendVerificationEmail.mockResolvedValue({ error: 'rate limited' });
    renderLogin();
    const user = await fillAndSubmit();

    await user.click(
      await screen.findByRole('button', { name: /resend verification/i }),
    );

    expect(await screen.findByText(/could not resend/i)).toBeVisible();
  });
});
