import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

// Control the reduced-motion signal per test. This file's mock replaces the global setup mock
// (which forces reduced motion on) so we can exercise the animated (motion-on) branch too.
const { useReducedMotion } = vi.hoisted(() => ({ useReducedMotion: vi.fn() }));
vi.mock('framer-motion', () => ({ useReducedMotion }));

import { useCountUp } from '@/lib/use-count-up';

afterEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

describe('useCountUp', () => {
  it('shows the final value immediately when reduced motion is preferred', () => {
    useReducedMotion.mockReturnValue(true);
    const { result } = renderHook(() => useCountUp(7, 600));
    expect(result.current).toBe(7);
  });

  it('animates from 0 up to the target, decelerating into the total', () => {
    useReducedMotion.mockReturnValue(false);
    // Drive requestAnimationFrame by hand with explicit timestamps — deterministic, no wall clock.
    const callbacks: FrameRequestCallback[] = [];
    vi.spyOn(globalThis, 'requestAnimationFrame').mockImplementation((cb) => {
      callbacks.push(cb);
      return callbacks.length;
    });
    vi.spyOn(globalThis, 'cancelAnimationFrame').mockImplementation(() => {});

    const { result } = renderHook(() => useCountUp(100, 600));
    const step = (now: number) =>
      act(() => callbacks[callbacks.length - 1](now));

    // Starts at zero before the first frame settles the clock.
    expect(result.current).toBe(0);
    step(0); // establishes the start timestamp
    expect(result.current).toBe(0);

    step(300); // halfway through the duration → partway up the total
    expect(result.current).toBeGreaterThan(0);
    expect(result.current).toBeLessThan(100);

    step(600); // duration elapsed → lands exactly on the target
    expect(result.current).toBe(100);
  });

  it('cancels its pending frame on unmount', () => {
    useReducedMotion.mockReturnValue(false);
    vi.spyOn(globalThis, 'requestAnimationFrame').mockReturnValue(42);
    const cancel = vi
      .spyOn(globalThis, 'cancelAnimationFrame')
      .mockImplementation(() => {});

    const { unmount } = renderHook(() => useCountUp(5, 600));
    unmount();
    expect(cancel).toHaveBeenCalledWith(42);
  });
});
