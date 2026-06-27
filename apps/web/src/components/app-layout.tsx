/**
 * Authenticated app shell: a header (brand + theme toggle + account slot), a sidebar of primary
 * navigation, and a content region that renders the active route via `<Outlet />`.
 *
 * This is the layout every signed-in screen (Generate / Review / Discover / Languages / Settings /
 * Account) renders inside. It is mounted behind `RequireAuth` (group 4.3), so it only ever renders
 * for an authenticated user; the header carries the theme toggle and the account / sign-out menu.
 */
import { Link, NavLink, Outlet } from 'react-router-dom';

import { ActiveLanguageProvider } from '@/components/active-language-provider';
import { CefrPanel } from '@/components/cefr-panel';
import { LanguagePicker } from '@/components/language-picker';
import { NAV_ITEMS } from '@/components/nav-items';
import { ThemeToggle } from '@/components/theme-toggle';
import { UserMenu } from '@/components/user-menu';
import { cn } from '@/lib/utils';

export function AppLayout() {
  return (
    <ActiveLanguageProvider>
      <div className="flex min-h-screen flex-col bg-background text-foreground">
        <header className="flex h-14 items-center justify-between gap-4 border-b px-4">
          <div className="flex items-center gap-4">
            <Link to="/" className="text-lg font-bold tracking-tight">
              Lengua
            </Link>
            <LanguagePicker />
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <UserMenu />
          </div>
        </header>

        <div className="flex flex-1">
          <aside className="hidden w-56 shrink-0 flex-col gap-4 border-r p-3 sm:flex">
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
            <CefrPanel />
          </aside>

          <main className="flex-1 p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </ActiveLanguageProvider>
  );
}
