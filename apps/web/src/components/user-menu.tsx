/**
 * Header account controls: an avatar-circle popover (email + Account / Settings links) and the
 * sign-out button.
 *
 * CONTRACT: the inline "Sign out" button stays the app's single at-mount `button "Sign out"` in the
 * header banner — App.test.tsx and the staging specs click it via
 * `getByRole('banner').getByRole('button', { name: 'Sign out' })` with no menu open, so it must
 * never move inside the popover. The popover is purely additive (it replaced the raw email span).
 *
 * Sign-out clears the Supabase session via `signOut()`; the resulting SIGNED_OUT event is handled
 * centrally in `AuthProvider` (which resets the TanStack Query cache) and flips the auth context to
 * signed-out, so `RequireAuth` redirects to `/login`. This component therefore only needs to call
 * `signOut()` — the cache reset + redirect happen automatically.
 */
import { useState } from 'react';
import { LogOut, Settings as SettingsIcon, User } from 'lucide-react';
import { Link } from 'react-router-dom';

import { useAuth } from '@/components/auth-context';
import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverClose,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { signOut } from '@/lib/auth';

const MENU_LINKS = [
  { to: '/account', label: 'Account', icon: User },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
];

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
      <Popover>
        <PopoverTrigger
          aria-label="Account menu"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-hig-blue/15 text-[12px] font-semibold text-hig-blue-deep transition duration-150 ease-apple active:scale-[0.92] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          {user?.email?.[0]?.toUpperCase() ?? '?'}
        </PopoverTrigger>
        <PopoverContent align="end" sideOffset={8} className="w-64">
          {user?.email !== undefined && (
            <>
              <div className="px-3 py-2">
                <p
                  className="truncate text-subhead font-medium"
                  title={user.email}
                >
                  {user.email}
                </p>
                <p className="text-footnote text-muted-foreground">Signed in</p>
              </div>
              <div className="mx-1 h-px bg-border" aria-hidden="true" />
            </>
          )}
          <div className="py-1">
            {MENU_LINKS.map(({ to, label, icon: Icon }) => (
              <PopoverClose key={to} asChild>
                <Link
                  to={to}
                  className="flex h-9 items-center gap-2 rounded-md px-3 text-body transition-colors duration-150 hover:bg-accent"
                >
                  <Icon
                    className="h-4 w-4 text-muted-foreground"
                    aria-hidden="true"
                  />
                  {label}
                </Link>
              </PopoverClose>
            ))}
          </div>
        </PopoverContent>
      </Popover>
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
