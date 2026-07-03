/**
 * `useCountUp` — animate a whole number up from 0 to `target` over `durationMs`, decelerating into
 * the final tally. The little "counting up" flourish on the review session-complete screen (spec §6).
 *
 * Honours the user's reduced-motion preference: when reduced motion is on (or the test environment
 * reports it), the final value is shown immediately with no animation, so a synchronous read always
 * observes `target`. Driven by requestAnimationFrame (not a timer) and cancelled on unmount.
 */
import { useEffect, useState } from 'react';
import { useReducedMotion } from 'framer-motion';

export function useCountUp(target: number, durationMs = 600): number {
  const reduced = useReducedMotion();
  const [value, setValue] = useState(() => (reduced ? target : 0));

  useEffect(() => {
    if (reduced) {
      // Skip the animation entirely — land on the final value.
      setValue(target);
      return;
    }
    let frame = 0;
    let start: number | null = null;
    const tick = (now: number) => {
      if (start === null) {
        start = now;
      }
      const progress = Math.min(1, (now - start) / durationMs);
      // Ease-out cubic so it decelerates as it approaches the total.
      const eased = 1 - (1 - progress) ** 3;
      setValue(Math.round(eased * target));
      if (progress < 1) {
        frame = requestAnimationFrame(tick);
      } else {
        setValue(target);
      }
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, durationMs, reduced]);

  return value;
}
