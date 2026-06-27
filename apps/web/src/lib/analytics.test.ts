import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ANALYTICS_CONSENT_KEY,
  analyticsKey,
  applyAnalyticsConsent,
  captureAnalytics,
  initAnalytics,
  persistConsent,
  readConsent,
  resetAnalytics,
  setAnalyticsCapturer,
  setAnalyticsConsentApplier,
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

/** Boot analytics (granted + key + a spy initializer) so `captureAnalytics` is allowed to fire. */
function boot() {
  setAnalyticsInitializer(vi.fn());
  persistConsent('granted');
  expect(initAnalytics({ env: KEY_ENV })).toBe(true);
}

describe('captureAnalytics', () => {
  it('drops events before the SDK is booted (the privacy guarantee)', () => {
    const capture = vi.fn();
    setAnalyticsCapturer(capture);
    persistConsent('granted'); // granted, but never booted (no initAnalytics)
    captureAnalytics('signup', { method: 'email' });
    expect(capture).not.toHaveBeenCalled();
  });

  it('forwards the event + properties once booted and granted', () => {
    boot();
    const capture = vi.fn();
    setAnalyticsCapturer(capture);
    captureAnalytics('signup', { method: 'email' });
    expect(capture).toHaveBeenCalledTimes(1);
    expect(capture).toHaveBeenCalledWith('signup', { method: 'email' });
  });

  it('drops events after an opt-out, even though the SDK stays booted', () => {
    boot();
    const capture = vi.fn();
    setAnalyticsCapturer(capture);
    // User opts out in Settings — the persisted decision flips to denied.
    persistConsent('denied');
    captureAnalytics('review', { rating: 3 });
    expect(capture).not.toHaveBeenCalled();
  });

  it('reads consent from an injected storage', () => {
    boot();
    const capture = vi.fn();
    setAnalyticsCapturer(capture);
    const storage = new Map<string, string>();
    // The injected storage has no decision → undecided → dropped, even though default storage granted.
    captureAnalytics(
      'generate',
      { word_count: 2 },
      {
        storage: {
          getItem: (k: string) => storage.get(k) ?? null,
        } as unknown as Storage,
      },
    );
    expect(capture).not.toHaveBeenCalled();
  });

  it('runs the default no-op capturer when none is registered (no throw)', () => {
    boot(); // booted + granted, but no capturer registered → exercises the default no-op
    expect(() => captureAnalytics('signup', { method: 'email' })).not.toThrow();
  });
});

describe('applyAnalyticsConsent', () => {
  it('on granted: boots once and resumes the live SDK (opt-in)', () => {
    const init = vi.fn();
    const applier = vi.fn();
    setAnalyticsInitializer(init);
    setAnalyticsConsentApplier(applier);
    persistConsent('granted');

    applyAnalyticsConsent('granted', { env: KEY_ENV });
    expect(init).toHaveBeenCalledTimes(1);
    expect(applier).toHaveBeenCalledWith(true);

    // A second apply (e.g. re-grant) does NOT re-init, but still resumes the SDK.
    applyAnalyticsConsent('granted', { env: KEY_ENV });
    expect(init).toHaveBeenCalledTimes(1);
    expect(applier).toHaveBeenLastCalledWith(true);
  });

  it('on denied: opts the live SDK out and never boots', () => {
    const init = vi.fn();
    const applier = vi.fn();
    setAnalyticsInitializer(init);
    setAnalyticsConsentApplier(applier);

    applyAnalyticsConsent('denied', { env: KEY_ENV });
    expect(init).not.toHaveBeenCalled();
    expect(applier).toHaveBeenCalledWith(false);
  });

  it('on null (undecided): does nothing', () => {
    const init = vi.fn();
    const applier = vi.fn();
    setAnalyticsInitializer(init);
    setAnalyticsConsentApplier(applier);

    applyAnalyticsConsent(null, { env: KEY_ENV });
    expect(init).not.toHaveBeenCalled();
    expect(applier).not.toHaveBeenCalled();
  });

  it('runs the default no-op applier when none is registered (no throw)', () => {
    setAnalyticsInitializer(vi.fn());
    // Both branches invoke the default no-op consent applier.
    expect(() =>
      applyAnalyticsConsent('denied', { env: KEY_ENV }),
    ).not.toThrow();
    persistConsent('granted');
    expect(() =>
      applyAnalyticsConsent('granted', { env: KEY_ENV }),
    ).not.toThrow();
  });
});
