import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { signUpWithEmail } = vi.hoisted(() => ({ signUpWithEmail: vi.fn() }));
vi.mock('@/lib/auth', () => ({ signUpWithEmail }));
vi.mock('@/components/oauth-buttons', () => ({
  OAuthButtons: () => <div data-testid="oauth-buttons" />,
}));
// Spy the activation-funnel event so we can assert it fires only on a successful sign-up (5.9.2).
const { trackSignup } = vi.hoisted(() => ({ trackSignup: vi.fn() }));
vi.mock('@/lib/analytics-events', () => ({ trackSignup }));

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

  it('exposes exactly ONE heading (its h1) — the "Lengua" wordmark is not a heading', () => {
    renderSignup();
    expect(screen.getAllByRole('heading')).toHaveLength(1);
    expect(screen.getByText('Lengua')).toBeInTheDocument();
  });

  it('gives both password fields a hold-to-reveal toggle', () => {
    renderSignup();
    const password = screen.getByLabelText('Password') as HTMLInputElement;
    const confirm = screen.getByLabelText(
      'Confirm password',
    ) as HTMLInputElement;
    expect(password).toHaveAttribute('type', 'password');
    expect(confirm).toHaveAttribute('type', 'password');
    const toggles = screen.getAllByRole('button', { name: 'Show password' });
    expect(toggles).toHaveLength(2);

    // Holding the first toggle reveals only its own field.
    fireEvent.pointerDown(toggles[0]);
    expect(password).toHaveAttribute('type', 'text');
    expect(confirm).toHaveAttribute('type', 'password');
    fireEvent.pointerUp(toggles[0]);
    expect(password).toHaveAttribute('type', 'password');
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
    expect(trackSignup).not.toHaveBeenCalled();
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
    // The funnel signup event fires with no PII (just the method).
    expect(trackSignup).toHaveBeenCalledWith('email');
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
