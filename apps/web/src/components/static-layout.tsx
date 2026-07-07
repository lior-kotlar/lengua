/**
 * Shell for the PUBLIC static/content pages — Privacy, Support, and the external Delete-account form
 * (task 8.1.2 / 8.3.1). These are reachable without signing in (Google Play requires the deletion
 * path to be usable without the app), so they render outside both the app shell and the auth guard.
 *
 * A minimal branded header (a link back to the app + the theme toggle) sits above the routed content,
 * with the shared {@link Footer} below, so a visitor who lands here from a store listing or an emailed
 * link can still reach the app, Privacy, and Support.
 */
import { Link, Outlet } from 'react-router-dom';

import { Footer } from '@/components/footer';
import { ThemeToggle } from '@/components/theme-toggle';

export function StaticLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="flex h-14 items-center justify-between px-4 sm:px-6">
        <Link to="/" className="text-headline tracking-[-0.01em]">
          Lengua
        </Link>
        <ThemeToggle />
      </header>
      <main className="flex-1 px-4 py-8 sm:px-6 sm:py-12">
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}
