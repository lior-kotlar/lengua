import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
const { signOut } = vi.hoisted(() => ({ signOut: vi.fn() }));
vi.mock('@/components/auth-context', () => ({ useAuth }));
vi.mock('@/lib/auth', () => ({ signOut }));

import { UserMenu } from '@/components/user-menu';

beforeEach(() => {
  vi.clearAllMocks();
  signOut.mockResolvedValue({ error: null });
});

describe('UserMenu', () => {
  it('shows the signed-in email and signs out on click', async () => {
    useAuth.mockReturnValue({
      user: { email: 'demo@lengua.test' },
      session: {},
      loading: false,
    });
    const user = userEvent.setup();
    render(<UserMenu />);

    expect(screen.getByText('demo@lengua.test')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /sign out/i }));
    expect(signOut).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /sign out/i })).toBeEnabled(),
    );
  });

  it('omits the email when there is no user', () => {
    useAuth.mockReturnValue({ user: null, session: null, loading: false });
    render(<UserMenu />);
    expect(screen.queryByText(/@/)).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /sign out/i }),
    ).toBeInTheDocument();
  });
});
