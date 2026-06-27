import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import type { AuthChangeEvent, Session } from '@supabase/supabase-js';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getSupabaseClient, getSession, onAuthStateChange, unsubscribe } =
  vi.hoisted(() => ({
    getSupabaseClient: vi.fn(),
    getSession: vi.fn(),
    onAuthStateChange: vi.fn(),
    unsubscribe: vi.fn(),
  }));

vi.mock('@/lib/supabase', () => ({ getSupabaseClient }));

import { useAuth } from '@/components/auth-context';
import { AuthProvider } from '@/components/auth-provider';

let emit: (event: AuthChangeEvent, session: Session | null) => void;

function makeSession(email: string): Session {
  return { user: { email } } as unknown as Session;
}

function Probe() {
  const { session, user, loading } = useAuth();
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="email">{user?.email ?? 'none'}</span>
      <span data-testid="has-session">{String(session !== null)}</span>
    </div>
  );
}

function renderProvider(queryClient = new QueryClient()) {
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </QueryClientProvider>,
    ),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  getSupabaseClient.mockReturnValue({
    auth: { getSession, onAuthStateChange },
  });
  getSession.mockResolvedValue({ data: { session: null }, error: null });
  onAuthStateChange.mockImplementation(
    (cb: (event: AuthChangeEvent, session: Session | null) => void) => {
      emit = cb;
      return { data: { subscription: { unsubscribe } } };
    },
  );
});

describe('AuthProvider', () => {
  it('bootstraps the initial session and clears loading', async () => {
    getSession.mockResolvedValue({
      data: { session: makeSession('demo@lengua.test') },
      error: null,
    });

    renderProvider();

    await waitFor(() =>
      expect(screen.getByTestId('loading')).toHaveTextContent('false'),
    );
    expect(screen.getByTestId('email')).toHaveTextContent('demo@lengua.test');
    expect(screen.getByTestId('has-session')).toHaveTextContent('true');
  });

  it('updates session state on a SIGNED_IN auth event', async () => {
    renderProvider();
    await waitFor(() =>
      expect(screen.getByTestId('loading')).toHaveTextContent('false'),
    );
    expect(screen.getByTestId('email')).toHaveTextContent('none');

    act(() => emit('SIGNED_IN', makeSession('new@lengua.test')));

    expect(screen.getByTestId('email')).toHaveTextContent('new@lengua.test');
  });

  it('clears the query cache and session on SIGNED_OUT', async () => {
    const { queryClient } = renderProvider();
    queryClient.setQueryData(['me'], { id: 'u1' });
    await waitFor(() =>
      expect(screen.getByTestId('loading')).toHaveTextContent('false'),
    );
    act(() => emit('SIGNED_IN', makeSession('demo@lengua.test')));
    expect(screen.getByTestId('has-session')).toHaveTextContent('true');

    act(() => emit('SIGNED_OUT', null));

    expect(screen.getByTestId('has-session')).toHaveTextContent('false');
    expect(queryClient.getQueryData(['me'])).toBeUndefined();
  });

  it('degrades to signed-out when the Supabase client is unavailable', async () => {
    const consoleError = vi
      .spyOn(console, 'error')
      .mockImplementation(() => {});
    getSupabaseClient.mockImplementation(() => {
      throw new Error(
        'Missing required environment variable(s): VITE_SUPABASE_URL',
      );
    });

    renderProvider();

    await waitFor(() =>
      expect(screen.getByTestId('loading')).toHaveTextContent('false'),
    );
    expect(screen.getByTestId('has-session')).toHaveTextContent('false');
    expect(consoleError).toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it('unsubscribes from auth changes on unmount', async () => {
    const { unmount } = renderProvider();
    await waitFor(() =>
      expect(screen.getByTestId('loading')).toHaveTextContent('false'),
    );
    unmount();
    expect(unsubscribe).toHaveBeenCalledTimes(1);
  });
});
