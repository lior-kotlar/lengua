/**
 * Route guards driven by the auth context (task 4.3.6).
 *
 * - {@link RequireAuth} wraps the authenticated app routes: it waits for the initial session check
 *   (no premature redirect), sends signed-out users to `/login` (remembering where they were
 *   heading), and otherwise renders the nested routes.
 * - {@link RedirectIfAuthed} wraps the public auth routes (login / signup / forgot-password): a
 *   signed-in user is bounced to the app, and — because the login/sign-up forms just establish a
 *   session — this is also what redirects the user *after* a successful login (the form itself
 *   doesn't navigate). The reset-password + callback routes are intentionally NOT wrapped, since
 *   they legitimately run with a transient recovery/verification session.
 *
 * Both guards use `replace` so the guarded URL never pollutes the history stack (no back-button loop).
 */
import { Loader2 } from 'lucide-react';
import {
  Navigate,
  Outlet,
  useLocation,
  type Location,
  type To,
} from 'react-router-dom';

import { useAuth } from '@/components/auth-context';

/** Centered spinner shown while the initial session is being read. */
export function RouteLoader() {
  return (
    <div
      role="status"
      aria-label="Loading"
      className="flex min-h-screen items-center justify-center bg-background text-foreground"
    >
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  );
}

/** Where a `RequireAuth` redirect stashes the originally-requested location. */
interface FromState {
  from?: Location;
}

/** Gate the authenticated app: redirect to `/login` (remembering the target) when signed out. */
export function RequireAuth() {
  const { session, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <RouteLoader />;
  }
  if (session === null) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <Outlet />;
}

/** Gate the public auth routes: redirect an already-signed-in user back into the app. */
export function RedirectIfAuthed() {
  const { session, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <RouteLoader />;
  }
  if (session !== null) {
    // Preserve the FULL originally-requested location — pathname AND search + hash — not just the
    // pathname, so a deep link like `/review?tab=due#card-3` survives the login round-trip.
    const from = (location.state as FromState | null)?.from;
    const target: To =
      from !== undefined
        ? { pathname: from.pathname, search: from.search, hash: from.hash }
        : '/';
    return <Navigate to={target} replace />;
  }
  return <Outlet />;
}
