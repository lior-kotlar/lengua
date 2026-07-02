import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
const { signOut } = vi.hoisted(() => ({ signOut: vi.fn() }));
vi.mock('@/components/auth-context', () => ({ useAuth }));
vi.mock('@/lib/auth', () => ({ signOut }));

import { UserMenu } from '@/components/user-menu';

function renderMenu() {
  return render(
    <MemoryRouter>
      <UserMenu />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  signOut.mockResolvedValue({ error: null });
});

describe('UserMenu', () => {
  it('signs out via the inline banner button, without opening any menu', async () => {
    useAuth.mockReturnValue({
      user: { email: 'demo@lengua.test' },
      session: {},
      loading: false,
    });
    const user = userEvent.setup();
    renderMenu();

    // CONTRACT: the sign-out button is reachable at mount (no popover open) — the staging specs
    // click it directly from the banner.
    await user.click(screen.getByRole('button', { name: /sign out/i }));
    expect(signOut).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /sign out/i })).toBeEnabled(),
    );
  });

  it('shows the email and Account/Settings links inside the avatar popover', async () => {
    useAuth.mockReturnValue({
      user: { email: 'demo@lengua.test' },
      session: {},
      loading: false,
    });
    const user = userEvent.setup();
    renderMenu();

    // The raw email span is gone from the header; it now lives inside the popover.
    expect(screen.queryByText('demo@lengua.test')).not.toBeInTheDocument();

    const avatar = screen.getByRole('button', { name: 'Account menu' });
    expect(avatar).toHaveTextContent('D'); // first letter of the email
    await user.click(avatar);

    expect(screen.getByText('demo@lengua.test')).toBeInTheDocument();
    expect(screen.getByText('Signed in')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Account' })).toHaveAttribute(
      'href',
      '/account',
    );
    expect(screen.getByRole('link', { name: 'Settings' })).toHaveAttribute(
      'href',
      '/settings',
    );
  });

  it('closes the popover when a menu link is clicked', async () => {
    useAuth.mockReturnValue({
      user: { email: 'demo@lengua.test' },
      session: {},
      loading: false,
    });
    const user = userEvent.setup();
    renderMenu();

    await user.click(screen.getByRole('button', { name: 'Account menu' }));
    await user.click(screen.getByRole('link', { name: 'Settings' }));

    await waitFor(() =>
      expect(
        screen.queryByRole('link', { name: 'Settings' }),
      ).not.toBeInTheDocument(),
    );
  });

  it('omits the email block when there is no user', async () => {
    useAuth.mockReturnValue({ user: null, session: null, loading: false });
    const user = userEvent.setup();
    renderMenu();

    expect(
      screen.getByRole('button', { name: /sign out/i }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Account menu' }));
    expect(screen.queryByText(/@/)).not.toBeInTheDocument();
    expect(screen.queryByText('Signed in')).not.toBeInTheDocument();
    // The navigation links still render (the routes are auth-guarded anyway).
    expect(screen.getByRole('link', { name: 'Account' })).toBeInTheDocument();
  });
});
