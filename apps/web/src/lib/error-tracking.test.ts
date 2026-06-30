import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  DEBUG_ERROR_MESSAGE,
  DEFAULT_TRACES_SAMPLE_RATE,
  SENTRY_TEST_CAPTURES_KEY,
  type SentryLike,
  captureException,
  debugToolsEnabled,
  errorTrackingDsn,
  errorTrackingEnvironment,
  errorTrackingTracesSampleRate,
  initErrorTracking,
  resetErrorTracking,
  triggerDebugError,
} from '@/lib/error-tracking';

const DSN = 'https://public@o0.ingest.sentry.io/1';

/** A fake Sentry SDK recording how it was initialised + what it captured. */
function fakeSentry(): SentryLike & {
  initOptions: Record<string, unknown> | null;
  captured: unknown[];
} {
  return {
    initOptions: null,
    captured: [],
    init(options) {
      this.initOptions = options;
    },
    captureException(error) {
      this.captured.push(error);
    },
    browserTracingIntegration() {
      return { name: 'BrowserTracing' };
    },
  };
}

beforeEach(() => {
  resetErrorTracking();
});

afterEach(() => {
  delete (window as unknown as Record<string, unknown>)[
    SENTRY_TEST_CAPTURES_KEY
  ];
});

describe('errorTrackingDsn', () => {
  it('returns the configured DSN', () => {
    expect(errorTrackingDsn({ VITE_SENTRY_DSN_WEB: DSN })).toBe(DSN);
  });

  it('returns undefined when unset or blank', () => {
    expect(errorTrackingDsn({})).toBeUndefined();
    expect(errorTrackingDsn({ VITE_SENTRY_DSN_WEB: '   ' })).toBeUndefined();
  });

  it('reads import.meta.env by default (no DSN configured in tests)', () => {
    expect(errorTrackingDsn()).toBeUndefined();
  });
});

describe('debugToolsEnabled', () => {
  it('is true only for the explicit on values', () => {
    expect(debugToolsEnabled({ VITE_ENABLE_DEBUG_TOOLS: '1' })).toBe(true);
    expect(debugToolsEnabled({ VITE_ENABLE_DEBUG_TOOLS: 'true' })).toBe(true);
  });

  it('is false when unset or any other value', () => {
    expect(debugToolsEnabled({})).toBe(false);
    expect(debugToolsEnabled({ VITE_ENABLE_DEBUG_TOOLS: '0' })).toBe(false);
    expect(debugToolsEnabled({ VITE_ENABLE_DEBUG_TOOLS: 'yes' })).toBe(false);
  });

  it('reads import.meta.env by default (debug tools off in tests)', () => {
    expect(debugToolsEnabled()).toBe(false);
  });
});

describe('errorTrackingEnvironment', () => {
  it('prefers VITE_SENTRY_ENVIRONMENT over MODE (the S5 fix)', () => {
    // `vercel build` always reports MODE='production'; the explicit var must still win so a
    // staging build tags `staging`, not `production`.
    expect(
      errorTrackingEnvironment({
        VITE_SENTRY_ENVIRONMENT: 'staging',
        MODE: 'production',
      }),
    ).toBe('staging');
  });

  it('falls back to MODE when VITE_SENTRY_ENVIRONMENT is unset or blank', () => {
    expect(errorTrackingEnvironment({ MODE: 'production' })).toBe('production');
    expect(
      errorTrackingEnvironment({
        VITE_SENTRY_ENVIRONMENT: '   ',
        MODE: 'development',
      }),
    ).toBe('development');
  });

  it('is undefined when neither is set', () => {
    expect(errorTrackingEnvironment({})).toBeUndefined();
  });

  it('reads import.meta.env by default (no override configured in tests)', () => {
    // Vitest sets MODE='test'; no VITE_SENTRY_ENVIRONMENT → the MODE fallback is returned.
    expect(errorTrackingEnvironment()).toBe(import.meta.env.MODE);
  });
});

describe('errorTrackingTracesSampleRate', () => {
  it('parses VITE_SENTRY_TRACES_SAMPLE_RATE as a float', () => {
    expect(
      errorTrackingTracesSampleRate({ VITE_SENTRY_TRACES_SAMPLE_RATE: '0.1' }),
    ).toBe(0.1);
    expect(
      errorTrackingTracesSampleRate({ VITE_SENTRY_TRACES_SAMPLE_RATE: '0' }),
    ).toBe(0);
  });

  it('defaults to 1.0 when unset or blank', () => {
    expect(errorTrackingTracesSampleRate({})).toBe(DEFAULT_TRACES_SAMPLE_RATE);
    expect(DEFAULT_TRACES_SAMPLE_RATE).toBe(1.0);
    expect(
      errorTrackingTracesSampleRate({ VITE_SENTRY_TRACES_SAMPLE_RATE: '  ' }),
    ).toBe(1.0);
  });

  it('defaults to 1.0 when not a finite number', () => {
    expect(
      errorTrackingTracesSampleRate({ VITE_SENTRY_TRACES_SAMPLE_RATE: 'abc' }),
    ).toBe(DEFAULT_TRACES_SAMPLE_RATE);
  });

  it('reads import.meta.env by default (default rate in tests)', () => {
    expect(errorTrackingTracesSampleRate()).toBe(DEFAULT_TRACES_SAMPLE_RATE);
  });
});

describe('initErrorTracking', () => {
  it('does not initialise without a DSN (no-op, zero egress)', () => {
    const sentry = fakeSentry();
    expect(initErrorTracking({ env: {}, sentry })).toBe(false);
    expect(sentry.initOptions).toBeNull();
  });

  it('initialises Sentry with the expected options when a DSN is set', () => {
    const sentry = fakeSentry();
    expect(
      initErrorTracking({
        env: { VITE_SENTRY_DSN_WEB: DSN, MODE: 'production' },
        sentry,
      }),
    ).toBe(true);

    expect(sentry.initOptions).toMatchObject({
      dsn: DSN,
      environment: 'production',
      tracesSampleRate: 1.0,
      sendDefaultPii: false,
    });
    // Performance/Web-Vitals tracing is wired via browserTracingIntegration().
    expect(sentry.initOptions?.integrations).toEqual([
      { name: 'BrowserTracing' },
    ]);
  });

  it('tags environment + sample rate from the build-time Sentry vars (over MODE)', () => {
    const sentry = fakeSentry();
    initErrorTracking({
      env: {
        VITE_SENTRY_DSN_WEB: DSN,
        VITE_SENTRY_ENVIRONMENT: 'staging',
        VITE_SENTRY_TRACES_SAMPLE_RATE: '0.1',
        // MODE is 'production' under `vercel build`; the explicit vars must override it.
        MODE: 'production',
      },
      sentry,
    });
    expect(sentry.initOptions).toMatchObject({
      environment: 'staging',
      tracesSampleRate: 0.1,
    });
  });

  it('initialises at most once', () => {
    const sentry = fakeSentry();
    const env = { VITE_SENTRY_DSN_WEB: DSN };
    expect(initErrorTracking({ env, sentry })).toBe(true);
    expect(initErrorTracking({ env, sentry })).toBe(false);
  });
});

describe('captureException', () => {
  it('does nothing (no throw) when Sentry is not initialised and debug tools are off', () => {
    expect(() => captureException(new Error('x'), {})).not.toThrow();
  });

  it('forwards to Sentry once initialised', () => {
    const sentry = fakeSentry();
    initErrorTracking({ env: { VITE_SENTRY_DSN_WEB: DSN }, sentry });
    const error = new Error('boom');
    captureException(error, {});
    expect(sentry.captured).toEqual([error]);
  });

  it('records the capture on window when debug tools are enabled (E2E observability)', () => {
    captureException(new Error('observed'), { VITE_ENABLE_DEBUG_TOOLS: '1' });
    captureException('a string error', { VITE_ENABLE_DEBUG_TOOLS: '1' });
    const store = window as unknown as Record<string, string[]>;
    expect(store[SENTRY_TEST_CAPTURES_KEY]).toEqual([
      'observed',
      'a string error',
    ]);
  });

  it('reads import.meta.env by default and does not record (debug tools off in tests)', () => {
    captureException(new Error('quiet'));
    const store = window as unknown as Record<string, unknown>;
    expect(store[SENTRY_TEST_CAPTURES_KEY]).toBeUndefined();
  });
});

describe('triggerDebugError', () => {
  it('captures the error then throws it', () => {
    const capture = vi.fn();
    expect(() => triggerDebugError('kaboom', capture)).toThrow('kaboom');
    expect(capture).toHaveBeenCalledTimes(1);
    const captured = capture.mock.calls[0][0];
    expect(captured).toBeInstanceOf(Error);
    expect((captured as Error).message).toBe('kaboom');
  });

  it('defaults the message and uses the real capture chokepoint', () => {
    // No capture injected → exercises the default `capture = captureException` (a no-op here:
    // Sentry uninitialised + debug tools off), then throws the default message.
    expect(() => triggerDebugError()).toThrow(DEBUG_ERROR_MESSAGE);
  });
});
