import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock the lazily-imported posthog-js singleton with spies (covers the dynamic import() too).
const posthog = vi.hoisted(() => ({
  init: vi.fn(),
  capture: vi.fn(),
  opt_in_capturing: vi.fn(),
  opt_out_capturing: vi.fn(),
}));
vi.mock('posthog-js', () => ({ default: posthog }));

import {
  applyAnalyticsConsent,
  captureAnalytics,
  persistConsent,
  resetAnalytics,
} from '@/lib/analytics';
import {
  capturePostHog,
  initPostHog,
  POSTHOG_EU_HOST,
  POSTHOG_OPTIONS,
  registerPostHogAnalytics,
  resetPostHogForTests,
  setPostHogConsent,
} from '@/lib/posthog';

/** Flush the lazy-import promise chain (a macrotask drains all pending microtasks). */
const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

beforeEach(() => {
  localStorage.clear();
  resetAnalytics();
  resetPostHogForTests();
  vi.clearAllMocks();
});

describe('POSTHOG_OPTIONS', () => {
  it('targets the EU host with no incidental capture (PII-safe defaults)', () => {
    expect(POSTHOG_EU_HOST).toBe('https://eu.i.posthog.com');
    expect(POSTHOG_OPTIONS.api_host).toBe(POSTHOG_EU_HOST);
    expect(POSTHOG_OPTIONS.autocapture).toBe(false);
    expect(POSTHOG_OPTIONS.capture_pageview).toBe(false);
    expect(POSTHOG_OPTIONS.capture_pageleave).toBe(false);
    expect(POSTHOG_OPTIONS.disable_session_recording).toBe(true);
    expect(POSTHOG_OPTIONS.person_profiles).toBe('identified_only');
  });
});

describe('initPostHog', () => {
  it('lazily loads posthog-js and inits it with the key + EU options', async () => {
    initPostHog('phc_abc');
    await flush();
    expect(posthog.init).toHaveBeenCalledTimes(1);
    expect(posthog.init).toHaveBeenCalledWith('phc_abc', POSTHOG_OPTIONS);
  });
});

describe('capturePostHog', () => {
  it('is a no-op before the SDK is booted', async () => {
    capturePostHog('signup', { method: 'email' });
    await flush();
    expect(posthog.capture).not.toHaveBeenCalled();
  });

  it('forwards the event + properties once booted', async () => {
    initPostHog('phc_abc');
    capturePostHog('signup', { method: 'email' });
    await flush();
    expect(posthog.capture).toHaveBeenCalledWith('signup', { method: 'email' });
  });
});

describe('setPostHogConsent', () => {
  it('is a no-op before the SDK is booted', async () => {
    setPostHogConsent(false);
    await flush();
    expect(posthog.opt_out_capturing).not.toHaveBeenCalled();
    expect(posthog.opt_in_capturing).not.toHaveBeenCalled();
  });

  it('opts out on deny and back in on grant once booted', async () => {
    initPostHog('phc_abc');
    setPostHogConsent(false);
    await flush();
    expect(posthog.opt_out_capturing).toHaveBeenCalledTimes(1);
    expect(posthog.opt_in_capturing).not.toHaveBeenCalled();

    setPostHogConsent(true);
    await flush();
    expect(posthog.opt_in_capturing).toHaveBeenCalledTimes(1);
  });
});

describe('registerPostHogAnalytics (wired through the consent seam)', () => {
  it('boots + captures + opts out via the seam, only after consent', async () => {
    registerPostHogAnalytics();

    // Before consent: nothing loads or sends.
    captureAnalytics('signup', { method: 'email' });
    await flush();
    expect(posthog.init).not.toHaveBeenCalled();
    expect(posthog.capture).not.toHaveBeenCalled();

    // Opt in (with a key) → boots PostHog at the EU host + resumes capturing.
    persistConsent('granted');
    applyAnalyticsConsent('granted', { env: { VITE_POSTHOG_KEY: 'phc_xyz' } });
    await flush();
    expect(posthog.init).toHaveBeenCalledWith('phc_xyz', POSTHOG_OPTIONS);
    expect(posthog.opt_in_capturing).toHaveBeenCalled();

    // A captured event now reaches PostHog.
    captureAnalytics('review', { rating: 4 });
    await flush();
    expect(posthog.capture).toHaveBeenCalledWith('review', { rating: 4 });

    // Opt out → the live SDK is told to stop, and the seam drops further events.
    persistConsent('denied');
    applyAnalyticsConsent('denied');
    await flush();
    expect(posthog.opt_out_capturing).toHaveBeenCalled();

    posthog.capture.mockClear();
    captureAnalytics('review', { rating: 1 });
    await flush();
    expect(posthog.capture).not.toHaveBeenCalled();
  });
});
