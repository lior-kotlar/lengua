import * as React from 'react';
import * as SwitchPrimitives from '@radix-ui/react-switch';

import { cn } from '@/lib/utils';

/**
 * Pixel-exact iOS switch (51×31, green when on) over Radix — the ONE toggle control app-wide.
 * Radix emits `role="switch"` + `aria-checked` and passes aria wiring through, so accessible
 * names ("Show vowel marks", "Share anonymous usage analytics") survive verbatim.
 */
const Switch = React.forwardRef<
  React.ElementRef<typeof SwitchPrimitives.Root>,
  React.ComponentPropsWithoutRef<typeof SwitchPrimitives.Root>
>(({ className, ...props }, ref) => (
  <SwitchPrimitives.Root
    ref={ref}
    className={cn(
      'peer inline-flex h-[31px] w-[51px] shrink-0 items-center rounded-full bg-input p-[2px] transition-colors duration-200 ease-apple focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-hig-green',
      className,
    )}
    {...props}
  >
    <SwitchPrimitives.Thumb className="block h-[27px] w-[27px] translate-x-0 rounded-full bg-white shadow-[0_2px_4px_rgb(0_0_0/0.2),0_0_1px_rgb(0_0_0/0.12)] transition-transform duration-200 ease-apple data-[state=checked]:translate-x-[20px]" />
  </SwitchPrimitives.Root>
));
Switch.displayName = SwitchPrimitives.Root.displayName;

export { Switch };
