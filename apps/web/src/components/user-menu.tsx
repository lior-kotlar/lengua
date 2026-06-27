/**
 * Header account control (task 4.3.8): shows the signed-in email and a sign-out button.
 *
 * Sign-out clears the Supabase session via `signOut()`; the resulting SIGNED_OUT event is handled
 * centrally in `AuthProvider` (which resets the TanStack Query cache) and flips the auth context to
 * signed-out, so `RequireAuth` redirects to `/login`. This component therefore only needs to call
 * `signOut()` — the cache reset + redirect happen automatically.
 */
import { useState } from 'react';
import { LogOut } from 'lucide-react';

import { useAuth } from '@/components/auth-context';
import { Button } from '@/components/ui/button';
import { signOut } from '@/lib/auth';

export function UserMenu() {
  const { user } = useAuth();
  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut() {
    setSigningOut(true);
    try {
      // No navigation here: the SIGNED_OUT event drives the cache reset + redirect-to-login.
      await signOut();
    } finally {
      // Re-enable if sign-out failed; on success the redirect unmounts this (the set is a no-op).
      setSigningOut(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      {user?.email !== undefined && (
        <span
          className="hidden max-w-[12rem] truncate text-sm text-muted-foreground sm:inline"
          title={user.email}
        >
          {user.email}
        </span>
      )}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => void handleSignOut()}
        disabled={signingOut}
      >
        <LogOut className="h-4 w-4" aria-hidden="true" />
        <span>Sign out</span>
      </Button>
    </div>
  );
}
