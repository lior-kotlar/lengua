/**
 * Minimal shell for the unauthenticated auth routes (login / signup / reset). Centers a card-width
 * column on the grouped background with a fixed radial wash behind it (§1.1); no app sidebar/nav.
 * The brand wordmark now lives on the card itself (AuthCard) above each screen's h1, so the header
 * carries only the theme toggle.
 */
import { Outlet } from 'react-router-dom';

import { Footer } from '@/components/footer';
import { ThemeToggle } from '@/components/theme-toggle';

export function AuthLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-background bg-[radial-gradient(60%_50%_at_50%_0%,hsl(var(--primary)/0.06),transparent)] bg-fixed text-foreground">
      <header className="flex h-14 items-center justify-end px-4 sm:px-6">
        <ThemeToggle />
      </header>
      <main className="flex flex-1 items-center justify-center p-6">
        <div className="w-full max-w-[400px]">
          <Outlet />
        </div>
      </main>
      <Footer />
    </div>
  );
}
