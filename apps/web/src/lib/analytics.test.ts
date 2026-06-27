import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ANALYTICS_CONSENT_KEY,
  analyticsKey,
  initAnalytics,
  persistConsent,
  readConsent,
  resetAnalytics,
  setAnalyticsInitializer,
} from '@/lib/analytics';

const KEY_ENV = { VITE_POSTHOG_KEY: 'phc_test' };

beforeEach(() => {
  localStorage.clear();
  resetAnalytics();
});

describe('readConsent / persistConsent', () => {
  it('returns null when nothing is stored (undecided)', () => {
    expect(readConsent()).toBeNull();
  });

  it('round-trips a granted then denied decision', () => {
    persistConsent('granted');
    expect(localStorage.getItem(ANALYTICS_CONSENT_KEY)).toBe('granted');
    expect(readConsent()).toBe('granted');

    persistConsent('denied');
    expect(readConsent()).toBe('denied');
  });

  it('treats a garbage stored value as undecided', () => {
    localStorage.setItem(ANALYTICS_CONSENT_KEY, 'maybe');
    expect(readConsent()).toBeNull();
  });
});

describe('analyticsKey', () => {
  it('returns the configured key', () => {
    expect(analyticsKey({ VITE_POSTHOG_KEY: 'phc_x' })).toBe('phc_x');
  });

  it('returns undefined when unset or blank', () => {
    expect(analyticsKey({})).toBeUndefined();
    expect(analyticsKey({ VITE_POSTHOG_KEY: '   ' })).toBeUndefined();
  });

  it('reads import.meta.env by default (no analytics key configured in tests)', () => {
    expect(analyticsKey()).toBeUndefined();
  });
});

describe('initAnalytics', () => {
  it('does not initialise before consent (the privacy guarantee)', () => {
    const init = vi.fn();
    setAnalyticsInitializer(init);
    expect(initAnalytics({ env: KEY_ENV })).toBe(false);
    expect(init).not.toHaveBeenCalled();
  });

  it('does not initialise when consent is denied', () => {
    const init = vi.fn();
    setAnalyticsInitializer(init);
    persistConsent('denied');
    expect(initAnalytics({ env: KEY_ENV })).toBe(false);
    expect(init).not.toHaveBeenCalled();
  });

  it('initialises exactly once when granted and a key is configured', () => {
    const init = vi.fn();
    setAnalyticsInitializer(init);
    persistConsent('granted');

    expect(initAnalytics({ env: KEY_ENV })).toBe(true);
    expect(init).toHaveBeenCalledTimes(1);
    expect(init).toHaveBeenCalledWith('phc_test');

    // Idempotent: a second call boots nothing.
    expect(initAnalytics({ env: KEY_ENV })).toBe(false);
    expect(init).toHaveBeenCalledTimes(1);
  });

  it('does not initialise when granted but no key is configured (clean seam)', () => {
    const init = vi.fn();
    setAnalyticsInitializer(init);
    persistConsent('granted');
    expect(initAnalytics({ env: {} })).toBe(false);
    expect(init).not.toHaveBeenCalled();
  });

  it('runs the default no-op initializer when granted with a key (no spy registered)', () => {
    persistConsent('granted');
    // No setAnalyticsInitializer → exercises the default no-op; still reports it booted once.
    expect(initAnalytics({ env: KEY_ENV })).toBe(true);
    expect(initAnalytics({ env: KEY_ENV })).toBe(false);
  });
});
