/**
 * Mobile bottom tab bar — the second list inside the single `nav[aria-label="Primary"]` landmark
 * (see app-layout.tsx). `fixed` frees it from its DOM position, so it pins to the bottom edge on
 * phones while the desktop sidebar list owns `sm:` and up. Four core-loop destinations + the More
 * sheet; 49px iOS-standard height plus the home-indicator safe area.
 *
 * The bar never hides (not even mid-review): losing navigation while a review card is up is a
 * nav trap, per the redesign spec §4.
 */
import { NavLink } from 'react-router-dom';

import { MoreSheet } from '@/components/more-sheet';
import { MOBILE_TAB_ITEMS } from '@/components/nav-items';
import { cn } from '@/lib/utils';

export function MobileTabBar() {
  return (
    <ul
      data-testid="nav-mobile"
      className="frosted fixed inset-x-0 bottom-0 z-40 flex h-[calc(49px+env(safe-area-inset-bottom))] border-t pb-[env(safe-area-inset-bottom)] sm:hidden"
    >
      {MOBILE_TAB_ITEMS.map(({ to, label, icon: Icon }) => (
        <li key={to} className="min-w-0 flex-1">
          <NavLink
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              cn(
                'flex h-full w-full flex-col items-center justify-center gap-0.5 transition duration-150 ease-apple active:scale-[0.92]',
                isActive ? 'text-primary' : 'text-muted-foreground',
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon className="h-6 w-6 stroke-[1.8]" aria-hidden="true" />
                {/* The 10px label needs the AA-contrast deep hue in light mode (it re-points to
                    the vivid blue in dark); the 24px icon stays at the brand primary. */}
                <span
                  className={cn(
                    'text-[10px] font-medium',
                    isActive && 'text-hig-blue-deep',
                  )}
                >
                  {label}
                </span>
              </>
            )}
          </NavLink>
        </li>
      ))}
      <li className="min-w-0 flex-1">
        <MoreSheet />
      </li>
    </ul>
  );
}
