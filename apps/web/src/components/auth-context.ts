/**
 * Auth context + `useAuth()` hook.
 *
 * Kept separate from the `<AuthProvider>` component (like `use-theme.ts`) so this module exports no
 * mix of components and non-components — keeps react-refresh / fast-refresh happy and lets screens
 * import the hook without pulling in the provider.
 */
import { createContext, useContext } from 'react';
import type { Session, User } from '@supabase/supabase-js';

export interface AuthState {
  /** The current session, or `null` when signed out. */
  session: Session | null;
  /** Convenience accessor for `session.user`, or `null` when signed out. */
  user: User | null;
  /** True until the initial session has been read from Supabase (avoids premature redirects). */
  loading: boolean;
}

export const AuthContext = createContext<AuthState | undefined>(undefined);

/** Access the current auth state. Throws if used outside an `<AuthProvider>`. */
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (ctx === undefined) {
    throw new Error('useAuth must be used within an <AuthProvider>');
  }
  return ctx;
}
