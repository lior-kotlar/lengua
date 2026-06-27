/**
 * Auth provider — the single source of truth for the signed-in session.
 *
 * On mount it reads the existing Supabase session and subscribes to auth-state changes
 * (`onAuthStateChange`), exposing `{ session, user, loading }` via {@link AuthContext}. `loading`
 * stays true until the first session read resolves, so route guards never bounce a logged-in user
 * to `/login` during the initial async check (task 4.3.6).
 *
 * On SIGNED_OUT it resets the TanStack Query cache (task 4.3.8) so no previous user's data lingers.
 * Centralizing the reset here means every sign-out path — the header button, and the on-401
 * refresh-failure sign-out in the API client — clears the cache without each caller remembering to.
 */
import { useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { Session } from '@supabase/supabase-js';

import { AuthContext, type AuthState } from '@/components/auth-context';
import { getSupabaseClient } from '@/lib/supabase';

export interface AuthProviderProps {
  children: React.ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    let supabase: ReturnType<typeof getSupabaseClient>;
    try {
      supabase = getSupabaseClient();
    } catch (error) {
      // Missing/invalid Supabase env (e.g. the intentionally env-less CI a11y build). Degrade to
      // signed-out so the SPA still renders (→ redirect to /login) instead of hanging on the
      // loader; readEnv's thrown message names the offending variable for a real misconfig.
      console.error('[auth] Supabase client unavailable:', error);
      setLoading(false);
      return;
    }

    // Initial read — resolves quickly from local storage (and, with detectSessionInUrl, after the
    // verification/OAuth hash is consumed). Either this or the first onAuthStateChange clears loading.
    void supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      setSession(data.session);
      setLoading(false);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, nextSession) => {
      if (!active) return;
      setSession(nextSession);
      setLoading(false);
      if (event === 'SIGNED_OUT') {
        // Drop every cached query so the next user starts clean (no cross-account leakage).
        queryClient.clear();
      }
    });

    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, [queryClient]);

  const value = useMemo<AuthState>(
    () => ({ session, user: session?.user ?? null, loading }),
    [session, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
