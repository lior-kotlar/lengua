/**
 * "More" slot of the mobile bottom tab bar: a trigger styled like the other tab slots that opens a
 * bottom sheet (Radix Dialog pinned to the bottom edge) holding the destinations that don't fit in
 * the bar — Languages / Settings / Account — plus an appearance (dark mode) row and the CefrPanel,
 * both otherwise unreachable below the `sm` breakpoint (the desktop sidebar and the header theme
 * toggle are hidden there).
 *
 * Deliberately NO "Sign out" row: the header banner button remains the app's single at-mount
 * sign-out control (pinned by App.test.tsx and the staging specs).
 */
import { useState } from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import { ChevronRight, Ellipsis, Moon } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';

import { CefrPanel } from '@/components/cefr-panel';
import { MORE_SHEET_ITEMS } from '@/components/nav-items';
import { Switch } from '@/components/ui/switch';
import { useTheme } from '@/components/use-theme';
import { cn } from '@/lib/utils';

function prefersDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

export function MoreSheet() {
  const [open, setOpen] = useState(false);
  const { theme, setTheme } = useTheme();
  const { pathname } = useLocation();
  const isDark = theme === 'dark' || (theme === 'system' && prefersDark());
  // The More slot lights up like a real tab while one of its sheet destinations is the route.
  const sectionActive = MORE_SHEET_ITEMS.some(({ to }) =>
    pathname.startsWith(to),
  );

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Trigger
        aria-label="More"
        className={cn(
          'flex h-full w-full flex-col items-center justify-center gap-0.5 transition duration-150 ease-apple active:scale-[0.92]',
          sectionActive ? 'text-primary' : 'text-muted-foreground',
        )}
      >
        <Ellipsis className="h-6 w-6 stroke-[1.8]" aria-hidden="true" />
        <span className="text-[10px] font-medium">More</span>
      </DialogPrimitive.Trigger>

      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:duration-200 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:duration-150" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          className="fixed inset-x-0 bottom-0 z-50 rounded-t-2xl bg-popover p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] text-popover-foreground shadow-overlay outline-none ease-apple data-[state=open]:animate-in data-[state=open]:slide-in-from-bottom data-[state=open]:duration-300 data-[state=closed]:animate-out data-[state=closed]:slide-out-to-bottom data-[state=closed]:duration-150"
        >
          <div
            className="mx-auto h-1 w-9 rounded-full bg-muted-foreground/30"
            aria-hidden="true"
          />
          <DialogPrimitive.Title className="sr-only">
            More
          </DialogPrimitive.Title>

          <ul className="mt-3 divide-y">
            {MORE_SHEET_ITEMS.map(({ to, label, icon: Icon }) => (
              <li key={to}>
                <Link
                  to={to}
                  onClick={() => setOpen(false)}
                  className="flex h-12 items-center gap-3 rounded-md px-2 text-body transition-colors duration-150 hover:bg-accent"
                >
                  <Icon
                    className="h-4 w-4 text-muted-foreground"
                    aria-hidden="true"
                  />
                  <span className="flex-1">{label}</span>
                  <ChevronRight
                    className="h-4 w-4 text-muted-foreground"
                    aria-hidden="true"
                  />
                </Link>
              </li>
            ))}
            <li className="flex h-12 items-center gap-3 px-2">
              <Moon
                className="h-4 w-4 text-muted-foreground"
                aria-hidden="true"
              />
              <label htmlFor="more-sheet-dark-mode" className="flex-1 text-body">
                Dark mode
              </label>
              <Switch
                id="more-sheet-dark-mode"
                checked={isDark}
                onCheckedChange={(on) => setTheme(on ? 'dark' : 'light')}
              />
            </li>
          </ul>

          <div className="mt-3">
            <CefrPanel />
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
