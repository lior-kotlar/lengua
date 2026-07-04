import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { requestPasswordReset } = vi.hoisted(() => ({
  requestPasswordReset: vi.fn(),
}));
vi.mock('@/lib/auth', () => ({ requestPasswordReset }));

import ForgotPassword from '@/pages/ForgotPassword';

function renderForgot() {
  return render(
    <MemoryRouter>
      <ForgotPassword />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  requestPasswordReset.mockResolvedValue({ error: null });
});

describe('ForgotPassword', () => {
  it('exposes exactly ONE heading (its h1) — the "Lengua" wordmark is not a heading', () => {
    renderForgot();
    expect(screen.getAllByRole('heading')).toHaveLength(1);
    expect(
      screen.getByRole('heading', { name: /reset password/i }),
    ).toBeInTheDocument();
    expect(screen.getByText('Lengua')).toBeInTheDocument();
  });

  it('validates the email before sending', async () => {
    const user = userEvent.setup();
    renderForgot();
    await user.type(screen.getByLabelText('Email'), 'not-an-email');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));
    expect(screen.getByText(/valid email/i)).toBeInTheDocument();
    expect(requestPasswordReset).not.toHaveBeenCalled();
  });

  it('shows the confirmation copy after sending', async () => {
    const user = userEvent.setup();
    renderForgot();
    await user.type(screen.getByLabelText('Email'), 'demo@lengua.test');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    expect(requestPasswordReset).toHaveBeenCalledWith('demo@lengua.test');
    expect(
      await screen.findByRole('heading', { name: /check your email/i }),
    ).toBeInTheDocument();
    expect(screen.getByText('demo@lengua.test')).toBeInTheDocument();
  });

  it('surfaces a server error', async () => {
    requestPasswordReset.mockResolvedValue({
      error: 'Too many attempts. Please wait a moment and try again.',
    });
    const user = userEvent.setup();
    renderForgot();
    await user.type(screen.getByLabelText('Email'), 'demo@lengua.test');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/too many/i);
  });
});
