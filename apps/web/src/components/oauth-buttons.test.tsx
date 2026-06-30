import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { signInWithProvider } = vi.hoisted(() => ({
  signInWithProvider: vi.fn(),
}));
vi.mock('@/lib/auth', () => ({ signInWithProvider }));

import { OAuthButtons } from '@/components/oauth-buttons';

beforeEach(() => {
  vi.clearAllMocks();
  signInWithProvider.mockResolvedValue({ error: null });
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('OAuthButtons', () => {
  it('enables Google but disables Apple ("(soon)") by default', () => {
    render(<OAuthButtons />);
    expect(
      screen.getByRole('button', { name: 'Continue with Google' }),
    ).toBeEnabled();
    // Apple is off by default because Supabase has external.apple=false — an enabled Apple button
    // would dead-end a real click on a raw 400 (finding S2). It renders disabled with "(soon)".
    const apple = screen.getByRole('button', { name: 'Continue with Apple' });
    expect(apple).toBeDisabled();
    expect(apple).toHaveTextContent('(soon)');
  });

  it('clicking the enabled Google button calls signInWithProvider(google)', async () => {
    const user = userEvent.setup();
    render(<OAuthButtons />);
    await user.click(
      screen.getByRole('button', { name: 'Continue with Google' }),
    );
    expect(signInWithProvider).toHaveBeenCalledWith('google');
  });

  it('VITE_OAUTH_PROVIDERS can re-enable Apple, whose click calls signInWithProvider(apple)', async () => {
    vi.stubEnv('VITE_OAUTH_PROVIDERS', 'google,apple');
    const user = userEvent.setup();
    render(<OAuthButtons />);
    const apple = screen.getByRole('button', { name: 'Continue with Apple' });
    expect(apple).toBeEnabled();
    await user.click(apple);
    expect(signInWithProvider).toHaveBeenCalledWith('apple');
  });

  it('shows an inline error when the provider call fails', async () => {
    signInWithProvider.mockResolvedValue({ error: 'Google is not enabled.' });
    const user = userEvent.setup();
    render(<OAuthButtons />);

    await user.click(
      screen.getByRole('button', { name: 'Continue with Google' }),
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Google is not enabled.',
    );
    // After a failure the buttons are interactive again.
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Continue with Google' }),
      ).toBeEnabled(),
    );
  });

  it('respects the disabled prop', () => {
    render(<OAuthButtons disabled />);
    expect(
      screen.getByRole('button', { name: 'Continue with Google' }),
    ).toBeDisabled();
  });

  it('disables a provider not listed in VITE_OAUTH_PROVIDERS', () => {
    vi.stubEnv('VITE_OAUTH_PROVIDERS', 'google');
    render(<OAuthButtons />);
    expect(
      screen.getByRole('button', { name: 'Continue with Google' }),
    ).toBeEnabled();
    const apple = screen.getByRole('button', { name: 'Continue with Apple' });
    expect(apple).toBeDisabled();
    expect(apple).toHaveTextContent('(soon)');
  });

  it('treats an empty VITE_OAUTH_PROVIDERS as none enabled', () => {
    vi.stubEnv('VITE_OAUTH_PROVIDERS', '');
    render(<OAuthButtons />);
    expect(
      screen.getByRole('button', { name: 'Continue with Google' }),
    ).toBeDisabled();
    expect(
      screen.getByRole('button', { name: 'Continue with Apple' }),
    ).toBeDisabled();
  });
});
