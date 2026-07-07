/**
 * Authenticated app shell: a frosted sticky header (brand + language pill + theme toggle + account
 * menu + sign out), ONE `nav[aria-label="Primary"]` landmark containing two lists — the desktop
 * sidebar (solid, `sm:` and up) and the fixed mobile bottom tab bar — and a content region that
 * renders the active route via `<Outlet />` with an enter-only page transition.
 *
 * Landmark discipline: jsdom (App.test.tsx) must see exactly one navigation named "Primary", and
 * Playwright's role engine excludes whichever list is display-hidden at the current viewport, so
 * `nav → link` queries stay unambiguous at both 390px and desktop. Unit tests that query nav links
 * must scope with `within(getByTestId('nav-desktop'))` (both lists render in jsdom).
 *
 * The header "Sign out" button (inside UserMenu) is a pinned contract — the single at-mount
 * `button "Sign out"` that App.test.tsx and the staging specs click with no menu open.
 */
import { m } from 'framer-motion';
import { Suspense } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';

import { ActiveLanguageProvider } from '@/components/active-language-provider';
import { CefrPanel } from '@/components/cefr-panel';
import { Footer } from '@/components/footer';
import { LanguagePicker } from '@/components/language-picker';
import { LoadingState } from '@/components/loading-state';
import { MobileTabBar } from '@/components/mobile-tab-bar';
import { NAV_ITEMS } from '@/components/nav-items';
import { ThemeToggle } from '@/components/theme-toggle';
import { UserMenu } from '@/components/user-menu';
import { VowelMarksProvider } from '@/components/vowel-marks-provider';
import { cn } from '@/lib/utils';

export function AppLayout() {
  const { pathname } = useLocation();

  return (
    <ActiveLanguageProvider>
      <VowelMarksProvider>
        <div className="flex min-h-screen flex-col bg-background text-foreground">
          <header className="frosted sticky top-0 z-40 flex h-[52px] items-center justify-between gap-4 border-b px-4 sm:px-6">
            <div className="flex min-w-0 items-center gap-3">
              <Link to="/" className="text-headline tracking-[-0.01em]">
                Lengua
              </Link>
              <LanguagePicker />
            </div>
            <div className="flex items-center gap-1">
              {/* Below `sm` the theme toggle lives in the More sheet instead. */}
              <ThemeToggle className="hidden h-8 w-8 sm:inline-flex" />
              <UserMenu />
            </div>
          </header>

          <div className="flex flex-1">
            <nav
              aria-label="Primary"
              className="z-40 sm:sticky sm:top-[52px] sm:flex sm:h-[calc(100vh-52px)] sm:w-60 sm:shrink-0 sm:flex-col sm:border-r"
            >
              {/* Desktop sidebar list (solid — no blur; content never scrolls beneath it). */}
              <ul
                data-testid="nav-desktop"
                className="hidden flex-1 flex-col gap-0.5 px-3 py-4 sm:flex"
              >
                {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
                  <li key={to}>
                    <NavLink
                      to={to}
                      end={to === '/'}
                      className={({ isActive }) =>
                        cn(
                          'flex h-9 items-center gap-2.5 rounded-md px-3 text-subhead font-medium transition duration-150 ease-apple active:scale-[0.98]',
                          isActive
                            ? 'bg-primary text-white'
                            : 'text-foreground/80 hover:bg-black/[0.04] dark:hover:bg-white/[0.06]',
                        )
                      }
                    >
                      <Icon
                        className="h-[18px] w-[18px] stroke-[1.8]"
                        aria-hidden="true"
                      />
                      {label}
                    </NavLink>
                  </li>
                ))}
              </ul>

              {/* Mobile tab bar list — `fixed` frees it from its DOM position here. */}
              <MobileTabBar />

              {/* CEFR level, desktop position (the More sheet carries it below `sm`). */}
              <div className="hidden px-3 pb-4 sm:block">
                <CefrPanel />
              </div>
            </nav>

            <main className="min-w-0 flex-1 px-4 py-6 pb-[calc(49px+env(safe-area-inset-bottom)+1.5rem)] sm:px-8 sm:py-10 sm:pb-10">
              {/* Enter-only page transition: keyed by pathname, no AnimatePresence and no exit
                  animation, so router behavior and page-level listeners are untouched. */}
              <m.div
                key={pathname}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2, ease: [0.32, 0.72, 0, 1] }}
              >
                {/* Route-level code splitting: the authenticated screens are React.lazy (App.tsx),
                    so a chunk load shows the shared skeleton here while the shell stays mounted. */}
                <Suspense fallback={<LoadingState label="Loading…" />}>
                  <Outlet />
                </Suspense>
              </m.div>
            </main>
          </div>

          {/* Site footer with the Privacy + Support links. Hidden below `sm`, where the fixed mobile
              tab bar owns the bottom edge; mobile users reach these from the Account screen. */}
          <Footer className="hidden sm:block" />
        </div>
      </VowelMarksProvider>
    </ActiveLanguageProvider>
  );
}
