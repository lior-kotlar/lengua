import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import type { ReactNode } from 'react';

// Make framer-motion deterministic in jsdom (the real `m`, `LazyMotion` and `MotionConfig` are
// kept). Two overrides:
//  - `AnimatePresence` renders its children immediately with NO exit animation, so advancing a
//    review card unmounts the old one synchronously — there is never a transient second
//    `card-answer` / rating pill from an in-flight exit that could break a query.
//  - `useReducedMotion` reports "on", so count-ups settle to their final value synchronously.
// Real enter/exit motion + the count-up animation are exercised in the staging walk, not jsdom.
vi.mock('framer-motion', async (importOriginal) => {
  const actual = await importOriginal<typeof import('framer-motion')>();
  const { createElement, Fragment } = await import('react');
  const AnimatePresence = ({ children }: { children?: ReactNode }) =>
    createElement(Fragment, null, children);
  return {
    ...actual,
    AnimatePresence:
      AnimatePresence as unknown as typeof actual.AnimatePresence,
    useReducedMotion: () => true,
  };
});

// jsdom does not implement matchMedia; the theme code reads prefers-color-scheme. Default to
// "light" (matches: false). Individual tests override window.matchMedia to exercise other branches.
if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

// jsdom does not implement ResizeObserver; Radix Popover (floating-ui positioning) requires it.
if (!window.ResizeObserver) {
  window.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

afterEach(() => {
  cleanup();
  localStorage.clear();
});
