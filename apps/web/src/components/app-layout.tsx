/**
 * Authenticated app shell: a header (brand + theme toggle + account slot), a sidebar of primary
 * navigation, and a content region that renders the active route via `<Outlet />`.
 *
 * This is the layout every signed-in screen (Generate / Review / Discover / Languages / Settings /
 * Account) renders inside. Route gating (redirect-to-login) lands in a later group (4.3); for now
 * the shell renders unconditionally so the structure + routing can be built and tested.
 */
import { Link, NavLink, Outlet } from 'react-router-dom';

import { NAV_ITEMS } from '@/components/nav-items';
import { ThemeToggle } from '@/components/theme-toggle';
import { cn } from '@/lib/utils';

export function AppLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="flex h-14 items-center justify-between border-b px-4">
        <Link to="/" className="text-lg font-bold tracking-tight">
          Lengua
        </Link>
        <div className="flex items-center gap-2">
          <ThemeToggle />
        </div>
      </header>

      <div className="flex flex-1">
        <aside className="hidden w-56 shrink-0 border-r p-3 sm:block">
          <nav aria-label="Primary" className="flex flex-col gap-1">
            {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-accent text-accent-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                  )
                }
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                {label}
              </NavLink>
            ))}
          </nav>
        </aside>

        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
