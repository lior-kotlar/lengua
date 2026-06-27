/**
 * Error tracking seam — Sentry for the web app (task 5.4.2).
 *
 * Mirrors the analytics seam ({@link ./analytics}) and the backend's `app/error_tracking.py`: Sentry
 * is initialised ONLY when a build-time, browser-safe DSN (`VITE_SENTRY_DSN_WEB`) is set. With no
 * DSN, {@link initErrorTracking} is a no-op — nothing loads, no events are sent (the dev/CI/E2E
 * path) — so a misconfigured or local build never reaches Sentry.
 *
 * The web app uses its OWN DSN, separate from the backend's `SENTRY_DSN_API`. It MUST be
 * `VITE_`-prefixed to be inlined into the bundle (a non-prefixed var can't reach client code) — see
 * the rename note in `apps/web/.env.example`.
 *
 * {@link captureException} is the single capture chokepoint. In a real (DSN-configured) build it
 * forwards to Sentry; additionally, when the debug tools are enabled (see {@link debugToolsEnabled},
 * a flag a production build never sets) it records the capture on `window` so an E2E step can assert
 * "the capture fired" with zero network egress, even when no DSN is configured.
 */
import * as Sentry from '@sentry/react';

/** `window` key the debug-tools build records captures on, for the E2E assertion (never in prod). */
export const SENTRY_TEST_CAPTURES_KEY = '__SENTRY_TEST_CAPTURES__';

/** Default debug-error message thrown by the hidden debug button / {@link triggerDebugError}. */
export const DEBUG_ERROR_MESSAGE = 'Sentry web debug test error';

/** The (optional) build-time config this seam reads. */
interface ErrorTrackingEnv {
  /** Browser Sentry DSN. Absent/blank → Sentry is disabled (nothing loads, zero egress). */
  VITE_SENTRY_DSN_WEB?: string;
  /** `'1'`/`'true'` enables the hidden debug-error button + capture recording (dev/test only). */
  VITE_ENABLE_DEBUG_TOOLS?: string;
  /** Vite mode (`development` / `production`), used as the Sentry `environment`. */
  MODE?: string;
}

/** The minimal Sentry surface this seam uses — lets tests inject a fake without a real SDK. */
export interface SentryLike {
  init(options: Record<string, unknown>): void;
  captureException(error: unknown): void;
  browserTracingIntegration(): unknown;
}

/** The configured browser Sentry DSN, or `undefined` when none is set (Sentry disabled). */
export function errorTrackingDsn(
  env: ErrorTrackingEnv = import.meta.env,
): string | undefined {
  const dsn = env.VITE_SENTRY_DSN_WEB;
  return dsn !== undefined && dsn.trim() !== '' ? dsn : undefined;
}

/**
 * Whether the hidden debug tools are enabled (the Sentry debug-error button + capture recording).
 *
 * Gated on the explicit build-time flag `VITE_ENABLE_DEBUG_TOOLS` (`'1'`/`'true'`), which defaults
 * OFF and a production build NEVER sets — so the debug button can never render or be triggered in a
 * deployed app. The E2E build sets it so the Playwright step can exercise the capture path.
 */
export function debugToolsEnabled(
  env: ErrorTrackingEnv = import.meta.env,
): boolean {
  const flag = env.VITE_ENABLE_DEBUG_TOOLS;
  return flag === '1' || flag === 'true';
}

let client: SentryLike | null = null;
let initialized = false;

/** Options for {@link initErrorTracking}; both default to the production sources. */
export interface InitErrorTrackingOptions {
  env?: ErrorTrackingEnv;
  /** Sentry SDK to initialise (defaults to `@sentry/react`); injected as a fake in tests. */
  sentry?: SentryLike;
}

/**
 * Initialise Sentry IFF a DSN is configured — at most once. Returns `true` on the call that
 * actually initialises, `false` otherwise (no DSN, or already initialised).
 *
 * Enables browser performance/Web-Vitals tracing via `browserTracingIntegration`. PII capture is
 * off (`sendDefaultPii: false`). With no DSN nothing initialises and no events are ever sent.
 */
export function initErrorTracking({
  env = import.meta.env,
  sentry = Sentry,
}: InitErrorTrackingOptions = {}): boolean {
  if (initialized) {
    return false;
  }
  const dsn = errorTrackingDsn(env);
  if (dsn === undefined) {
    return false;
  }
  sentry.init({
    dsn,
    environment: env.MODE,
    // Captures performance transactions + Web Vitals (LCP/CLS/INP/…). The owner tunes the volume
    // for prod via the Sentry project / a later env when the live DSN is wired (Phase 6).
    integrations: [sentry.browserTracingIntegration()],
    tracesSampleRate: 1.0,
    sendDefaultPii: false,
  });
  client = sentry;
  initialized = true;
  return true;
}

/**
 * Capture an error: forward to Sentry when initialised, and — when the debug tools are enabled —
 * record it on `window` so a Playwright step can assert the capture fired with zero egress.
 */
export function captureException(
  error: unknown,
  env: ErrorTrackingEnv = import.meta.env,
): void {
  if (client !== null) {
    client.captureException(error);
  }
  if (debugToolsEnabled(env)) {
    const store = window as unknown as Record<string, string[] | undefined>;
    const captures = store[SENTRY_TEST_CAPTURES_KEY] ?? [];
    captures.push(error instanceof Error ? error.message : String(error));
    store[SENTRY_TEST_CAPTURES_KEY] = captures;
  }
}

/**
 * Build an error, capture it, and throw it — the action behind the hidden debug button.
 *
 * It both captures explicitly (so the path is observable in E2E even with no DSN) AND throws the
 * same error (so a DSN-configured build also captures it via Sentry's global handler; Sentry's
 * default dedupe drops the duplicate). `capture` is injectable so the throw is unit-testable without
 * side effects.
 */
export function triggerDebugError(
  message: string = DEBUG_ERROR_MESSAGE,
  capture: (error: unknown) => void = captureException,
): never {
  const error = new Error(message);
  capture(error);
  throw error;
}

/** Reset the init seam (tests only): clears the once-guard and the client reference. */
export function resetErrorTracking(): void {
  client = null;
  initialized = false;
}
