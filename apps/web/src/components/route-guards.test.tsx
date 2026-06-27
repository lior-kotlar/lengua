import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { Session } from '@supabase/supabase-js';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// MemoryRouter's `initialEntries` element type (react-router-dom doesn't export `InitialEntry`).
type Entry =
  | string
  | { pathname: string; state?: { from?: { pathname: string } } };

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/components/auth-context', () => ({ useAuth }));

import {
  RedirectIfAuthed,
  RequireAuth,
  RouteLoader,
} from '@/components/route-guards';

const SESSION = { user: { email: 'demo@lengua.test' } } as unknown as Session;

function setAuth(state: { session: Session | null; loading: boolean }) {
  useAuth.mockReturnValue({
    ...state,
    user: state.session?.user ?? null,
  });
}

function renderProtected(initialEntries: Entry[]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route element={<RequireAuth />}>
          <Route path="/app" element={<div>Protected content</div>} />
        </Route>
        <Route path="/login" element={<div>Login screen</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderAuthRoute(initialEntries: Entry[]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route element={<RedirectIfAuthed />}>
          <Route path="/login" element={<div>Login form</div>} />
        </Route>
        <Route path="/" element={<div>Home screen</div>} />
        <Route path="/review" element={<div>Review screen</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('RouteLoader', () => {
  it('renders an accessible loading status', () => {
    render(<RouteLoader />);
    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
  });
});

describe('RequireAuth', () => {
  it('shows the loader while the session is still loading', () => {
    setAuth({ session: null, loading: true });
    renderProtected(['/app']);
    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
    expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
  });

  it('redirects to /login when signed out', () => {
    setAuth({ session: null, loading: false });
    renderProtected(['/app']);
    expect(screen.getByText('Login screen')).toBeInTheDocument();
    expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
  });

  it('renders the protected route when signed in', () => {
    setAuth({ session: SESSION, loading: false });
    renderProtected(['/app']);
    expect(screen.getByText('Protected content')).toBeInTheDocument();
  });
});

describe('RedirectIfAuthed', () => {
  it('shows the loader while loading', () => {
    setAuth({ session: null, loading: true });
    renderAuthRoute(['/login']);
    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
  });

  it('renders the auth form when signed out', () => {
    setAuth({ session: null, loading: false });
    renderAuthRoute(['/login']);
    expect(screen.getByText('Login form')).toBeInTheDocument();
  });

  it('redirects a signed-in user to home by default', () => {
    setAuth({ session: SESSION, loading: false });
    renderAuthRoute(['/login']);
    expect(screen.getByText('Home screen')).toBeInTheDocument();
  });

  it('redirects to the originally-requested location when present', () => {
    setAuth({ session: SESSION, loading: false });
    renderAuthRoute([
      { pathname: '/login', state: { from: { pathname: '/review' } } },
    ]);
    expect(screen.getByText('Review screen')).toBeInTheDocument();
  });
});
