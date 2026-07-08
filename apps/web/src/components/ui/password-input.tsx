import * as React from 'react';
import { Eye, EyeOff } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

/**
 * A password `Input` with an in-box "eye" control to check what was typed.
 *
 * Single source of truth: `show` drives the input `type` (`text` when revealed, `password`
 * otherwise). Two distinct, non-conflicting reveal paths:
 *  - Mouse / touch — HOLD to reveal: pointer-down shows, pointer-up/leave/cancel hides. We
 *    `preventDefault()` on pointer-down so the button doesn't steal focus from the field; the
 *    `click` that browsers still synthesize after release is inert because no `onClick` is bound
 *    (binding one would fight the hold).
 *  - Keyboard — TOGGLE: Enter/Space flips `show` (sticky, one flip per physical press — OS key
 *    auto-repeat is ignored), since press-and-hold isn't reachable by keyboard. `preventDefault()`
 *    on Space stops the page from scrolling. Losing focus resets to hidden so a password is never
 *    left revealed after tabbing away. A sticky reveal is only cancelled by a deliberate action
 *    (toggle again, a pointer hold ending, or blur) — a plain hover-out doesn't re-mask it.
 *
 * It accepts every `Input` prop except `type` (which it owns), so callers keep their `id`,
 * `autoComplete`, `aria-*`, `className`, etc. and the `<label htmlFor>` association is preserved.
 */
export type PasswordInputProps = Omit<React.ComponentProps<'input'>, 'type'>;

const PasswordInput = React.forwardRef<HTMLInputElement, PasswordInputProps>(
  ({ className, ...props }, ref) => {
    const [show, setShow] = React.useState(false);
    // True only between pointer-down and its release: gates the pointer re-mask handlers so a
    // plain hover-out (pointerleave fires without any button pressed) or a stray pointer-up can't
    // cancel a keyboard-toggled (sticky) reveal.
    const holding = React.useRef(false);
    const endHold = () => {
      if (holding.current) {
        holding.current = false;
        setShow(false);
      }
    };

    return (
      <div className="relative">
        <Input
          ref={ref}
          type={show ? 'text' : 'password'}
          // Reserve room on the right so revealed text never sits under the eye button.
          className={cn('pr-11', className)}
          {...props}
        />
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={show ? 'Hide password' : 'Show password'}
          className="absolute right-1 top-1/2 size-8 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          // Pointer HOLD (mouse/touch): reveal only while pressed.
          onPointerDown={(event) => {
            // Keep focus where it is (the click that still fires after release is harmless — no
            // onClick is bound).
            event.preventDefault();
            holding.current = true;
            setShow(true);
          }}
          onPointerUp={endHold}
          onPointerLeave={endHold}
          onPointerCancel={endHold}
          // Keyboard TOGGLE: Enter/Space flip visibility (only real key input reaches here, so it
          // never collides with the pointer-hold path above).
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              // Stop Space from scrolling the page; Enter must not submit the form (type="button"
              // already guarantees that).
              event.preventDefault();
              // One flip per physical press: ignore OS key auto-repeat so holding the key doesn't
              // strobe the reveal and land on a parity-dependent state.
              if (!event.repeat) {
                setShow((value) => !value);
              }
            }
          }}
          // Never leave a password revealed after the control loses focus.
          onBlur={() => {
            holding.current = false;
            setShow(false);
          }}
        >
          {show ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
        </Button>
      </div>
    );
  },
);
PasswordInput.displayName = 'PasswordInput';

export { PasswordInput };
