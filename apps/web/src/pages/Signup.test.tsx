import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { signUpWithEmail } = vi.hoisted(() => ({ signUpWithEmail: vi.fn() }));
vi.mock('@/lib/auth', () => ({ signUpWithEmail }));
vi.mock('@/components/oauth-buttons', () => ({
  OAuthButtons: () => <div data-testid="oauth-buttons" />,
}));

import Signup from '@/pages/Signup';

function renderSignup() {
  return render(
    <MemoryRouter>
      <Signup />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  signUpWithEmail.mockResolvedValue({ error: null, needsVerification: true });
});

describe('Signup', () => {
  it('renders the heading and OAuth buttons', () => {
    renderSignup();
    expect(
      screen.getByRole('heading', { name: /sign up/i }),
    ).toBeInTheDocument();
    expect(screen.getByTestId('oauth-buttons')).toBeInTheDocument();
  });

  it('blocks submission and shows field errors when invalid', async () => {
    const user = userEvent.setup();
    renderSignup();

    await user.type(screen.getByLabelText('Email'), 'demo@lengua.test');
    await user.type(screen.getByLabelText('Password'), 'Abcdef12');
    await user.type(screen.getByLabelText('Confirm password'), 'Different1');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    expect(screen.getByText(/do not match/i)).toBeInTheDocument();
    expect(signUpWithEmail).not.toHaveBeenCalled();
  });

  it('shows the verification notice after a successful sign-up', async () => {
    const user = userEvent.setup();
    renderSignup();

    await user.type(screen.getByLabelText('Email'), 'demo@lengua.test');
    await user.type(screen.getByLabelText('Password'), 'Abcdef12');
    await user.type(screen.getByLabelText('Confirm password'), 'Abcdef12');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    expect(signUpWithEmail).toHaveBeenCalledWith(
      'demo@lengua.test',
      'Abcdef12',
    );
    expect(
      await screen.findByRole('heading', { name: /check your email/i }),
    ).toBeInTheDocument();
    expect(screen.getByText('demo@lengua.test')).toBeInTheDocument();
  });

  it('surfaces a server error', async () => {
    signUpWithEmail.mockResolvedValue({
      error: 'An account with this email already exists.',
      needsVerification: false,
    });
    const user = userEvent.setup();
    renderSignup();

    await user.type(screen.getByLabelText('Email'), 'demo@lengua.test');
    await user.type(screen.getByLabelText('Password'), 'Abcdef12');
    await user.type(screen.getByLabelText('Confirm password'), 'Abcdef12');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /already exists/i,
    );
  });
});
