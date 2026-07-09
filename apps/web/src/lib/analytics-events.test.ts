import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  initAnalytics,
  persistConsent,
  resetAnalytics,
  setAnalyticsCapturer,
  setAnalyticsInitializer,
} from '@/lib/analytics';
import {
  ANALYTICS_EVENTS,
  trackGenerate,
  trackLanguageAdded,
  trackReview,
  trackSignup,
} from '@/lib/analytics-events';

/** Property keys that would be PII — events must never carry any of these. */
const PII_KEYS = ['email', 'name', 'username', 'words', 'word', 'sentence'];

const capture = vi.fn();

/** Boot analytics (granted + key + a spy initializer) and register the capture spy. */
function bootWithConsent() {
  setAnalyticsInitializer(vi.fn());
  setAnalyticsCapturer(capture);
  persistConsent('granted');
  initAnalytics({ env: { VITE_POSTHOG_KEY: 'phc_test' } });
}

beforeEach(() => {
  localStorage.clear();
  resetAnalytics();
  vi.clearAllMocks();
});

describe('activation funnel events', () => {
  it('exposes the four funnel step names in order', () => {
    expect(ANALYTICS_EVENTS).toEqual({
      signup: 'signup',
      languageAdded: 'language_added',
      generate: 'generate',
      review: 'review',
    });
  });

  it('fires all four named events with no PII when consent is granted', () => {
    bootWithConsent();

    trackSignup('email');
    trackLanguageAdded('es', true);
    trackGenerate(3);
    trackReview(4);

    expect(capture.mock.calls.map((c) => c[0])).toEqual([
      'signup',
      'language_added',
      'generate',
      'review',
    ]);

    // Exact, non-identifying payloads.
    expect(capture).toHaveBeenNthCalledWith(1, 'signup', { method: 'email' });
    expect(capture).toHaveBeenNthCalledWith(2, 'language_added', {
      code: 'es',
      curated: true,
    });
    expect(capture).toHaveBeenNthCalledWith(3, 'generate', { word_count: 3 });
    expect(capture).toHaveBeenNthCalledWith(4, 'review', { rating: 4 });

    // No event property is a PII field.
    for (const [, props] of capture.mock.calls) {
      for (const key of Object.keys(props ?? {})) {
        expect(PII_KEYS).not.toContain(key);
      }
    }
  });

  it('defaults the signup method to email and passes a null language code through', () => {
    bootWithConsent();
    trackSignup();
    trackLanguageAdded(null, false);
    expect(capture).toHaveBeenNthCalledWith(1, 'signup', { method: 'email' });
    expect(capture).toHaveBeenNthCalledWith(2, 'language_added', {
      code: null,
      curated: false,
    });
  });

  it('fires nothing before consent (the events are consent-gated)', () => {
    setAnalyticsCapturer(capture);
    // No consent / no boot.
    trackSignup('email');
    trackLanguageAdded('he', true);
    trackGenerate(1);
    trackReview(2);
    expect(capture).not.toHaveBeenCalled();
  });
});
