import * as React from 'react';

import { cn } from '@/lib/utils';

/**
 * A keyboard-hint chip ("Space", "1"…"4") rendered inside buttons and hint rows. ALWAYS
 * `aria-hidden`: the chip is a sighted-user affordance, and hiding it keeps button accessible
 * names byte-exact ("Show answer", "Again" …) for the pinned test contract.
 */
function Kbd({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      aria-hidden
      className={cn(
        'inline-flex min-w-[18px] items-center justify-center rounded-[5px] bg-black/[0.06] px-1 text-[11px] font-medium leading-[18px] tabular-nums dark:bg-white/10',
        className,
      )}
      {...props}
    >
      {children}
    </kbd>
  );
}

export { Kbd };
