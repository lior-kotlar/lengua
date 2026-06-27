import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { Session } from '@supabase/supabase-js';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// The route tree is gated by the auth context (RequireAuth / RedirectIfAuthed). Mock useAuth so each
// test controls whether a session exists, without standing up a real AuthProvider + Supabase.
const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/components/auth-context', () => ({ useAuth }));

import App from '@/App';
import { ThemeProvider } from '@/components/theme-provider';

const SESSION = {
  user: { email: 'demo@lengua.test' },
} as unknown as Session;

function setSession(session: Session | null) {
  useAuth.mockReturnValue({
    session,
    user: session?.user ?? null,
    loading: false,
  });
}

function renderAt(path: string) {
  return render(
    <ThemeProvider defaultTheme="light">
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('App routing — authenticated', () => {
  beforeEach(() => setSession(SESSION));

  it('mounts the Dashboard inside the app shell at /', () => {
    renderAt('/');
    expect(
      screen.getByRole('heading', { name: 'Dashboard' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('navigation', { name: 'Primary' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Lengua' })).toBeInTheDocument();
    // The account menu (sign out) is in the shell header.
    expect(
      screen.getByRole('button', { name: /sign out/i }),
    ).toBeInTheDocument();
  });

  it.each([
    ['/generate', 'Generate'],
    ['/review', 'Review'],
    ['/discover', 'Discover'],
    ['/languages', 'Languages'],
    ['/settings', 'Settings'],
    ['/account', 'Account'],
  ])('mounts the %s screen', (path, heading) => {
    renderAt(path);
    expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument();
  });
});

describe('App routing — unauthenticated', () => {
  beforeEach(() => setSession(null));

  it('redirects a protected route to the login screen', () => {
    renderAt('/');
    expect(
      screen.getByRole('heading', { name: /log in/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('navigation', { name: 'Primary' }),
    ).not.toBeInTheDocument();
  });

  it('mounts the Login screen in the auth shell at /login (no app nav)', () => {
    renderAt('/login');
    expect(
      screen.getByRole('heading', { name: /log in/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('navigation', { name: 'Primary' }),
    ).not.toBeInTheDocument();
  });

  it('mounts the Signup screen at /signup', () => {
    renderAt('/signup');
    expect(
      screen.getByRole('heading', { name: /sign up/i }),
    ).toBeInTheDocument();
  });

  it('mounts the forgot-password screen', () => {
    renderAt('/forgot-password');
    expect(
      screen.getByRole('heading', { name: /reset password/i }),
    ).toBeInTheDocument();
  });

  it('renders the 404 screen for an unknown route', () => {
    renderAt('/does-not-exist');
    expect(screen.getByRole('heading', { name: '404' })).toBeInTheDocument();
  });
});
