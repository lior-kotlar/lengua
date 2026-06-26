/**
 * Minimal shell for the unauthenticated auth routes (login / signup / reset). Centers a card-width
 * content column with the brand on top; no app sidebar/nav. The actual forms land in group 4.3.
 */
import { Outlet } from 'react-router-dom';

import { ThemeToggle } from '@/components/theme-toggle';

export function AuthLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="flex h-14 items-center justify-between px-4">
        <span className="text-lg font-bold tracking-tight">Lengua</span>
        <ThemeToggle />
      </header>
      <main className="flex flex-1 items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
