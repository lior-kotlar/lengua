/**
 * Analytics consent seam (group 4.10.3; PostHog wiring group 5.9).
 *
 * Product analytics (PostHog, EU-hosted) must NEVER load or collect anything until the user
 * explicitly opts in. This module is the single, provider-agnostic chokepoint that enforces that
 * contract — the concrete PostHog adapter lives in `lib/posthog.ts` and registers itself here:
 *
 *  - the decision (`granted` / `denied`) is persisted in localStorage, so the first-run banner is
 *    shown once and never re-prompts after a choice;
 *  - {@link initAnalytics} boots the analytics SDK at most once, and ONLY when consent is granted
 *    AND an analytics key is configured (`VITE_POSTHOG_KEY`). With no key, the choice still persists
 *    and nothing loads — a clean seam behind an env flag, so dev/CI/E2E never ship analytics;
 *  - {@link captureAnalytics} forwards an event to the SDK ONLY while booted AND consent is granted,
 *    so no event can ever be sent before opt-in (or after opt-out);
 *  - {@link applyAnalyticsConsent} is what the consent UI calls on every decision change: it boots
 *    (first opt-in) and resumes/pauses capturing on the live SDK (`opt_in`/`opt_out`).
 *
 * Everything PostHog-specific is injected ({@link setAnalyticsInitializer} / {@link
 * setAnalyticsCapturer} / {@link setAnalyticsConsentApplier}), so this consent logic stays
 * provider-agnostic and fully unit-testable, and the default implementations are no-ops — meaning a
 * build that never calls `registerPostHogAnalytics()` (or has no key) loads and sends nothing.
 */

/** The user's analytics choice. `null` (absent) means undecided — the consent banner shows. */
export type AnalyticsDecision = 'granted' | 'denied';

/** localStorage key for the persisted analytics decision. */
export const ANALYTICS_CONSENT_KEY = 'lengua.analytics-consent';

/** The (optional) build-time analytics config this seam reads. */
interface AnalyticsEnv {
  /** PostHog project key. Absent/blank → analytics is disabled (nothing loads). */
  VITE_POSTHOG_KEY?: string;
}

/** Read the persisted analytics decision, or `null` when the user has not decided yet. */
export function readConsent(
  storage: Storage = localStorage,
): AnalyticsDecision | null {
  const raw = storage.getItem(ANALYTICS_CONSENT_KEY);
  return raw === 'granted' || raw === 'denied' ? raw : null;
}

/** Persist the analytics decision so the banner never re-prompts once decided. */
export function persistConsent(
  decision: AnalyticsDecision,
  storage: Storage = localStorage,
): void {
  storage.setItem(ANALYTICS_CONSENT_KEY, decision);
}

/** The configured analytics key, or `undefined` when none is set (analytics disabled). */
export function analyticsKey(
  env: AnalyticsEnv = import.meta.env,
): string | undefined {
  const key = env.VITE_POSTHOG_KEY;
  return key !== undefined && key.trim() !== '' ? key : undefined;
}

/** Boots the analytics SDK with the configured key. Registered by `lib/posthog.ts` (or a test). */
export type AnalyticsInitializer = (key: string) => void;

/** Sends one event to the booted SDK. Registered by `lib/posthog.ts` (or a test). */
export type AnalyticsCapturer = (
  event: string,
  properties?: Record<string, unknown>,
) => void;

/** Resumes (`true`) or pauses (`false`) capturing on the live SDK. Registered by `lib/posthog.ts`. */
export type AnalyticsConsentApplier = (granted: boolean) => void;

// The real implementations live in `lib/posthog.ts` and `import('posthog-js')` lazily. Until
// `registerPostHogAnalytics()` runs (it never does in dev/CI/E2E without a key), these are no-ops:
// consent still gates them, but nothing loads or is sent.
function defaultInitializer(): void {
  /* no-op until the PostHog adapter registers the real loader */
}
function defaultCapturer(): void {
  /* no-op until the PostHog adapter registers the real capture */
}
function defaultConsentApplier(): void {
  /* no-op until the PostHog adapter registers opt-in/opt-out */
}

let initializer: AnalyticsInitializer = defaultInitializer;
let capturer: AnalyticsCapturer = defaultCapturer;
let consentApplier: AnalyticsConsentApplier = defaultConsentApplier;
let initialized = false;

/** Register the analytics initializer (the PostHog adapter, or a test spy). */
export function setAnalyticsInitializer(fn: AnalyticsInitializer): void {
  initializer = fn;
}

/** Register the event capturer (the PostHog adapter, or a test spy). */
export function setAnalyticsCapturer(fn: AnalyticsCapturer): void {
  capturer = fn;
}

/** Register the opt-in/opt-out applier (the PostHog adapter, or a test spy). */
export function setAnalyticsConsentApplier(fn: AnalyticsConsentApplier): void {
  consentApplier = fn;
}

/** Reset the seam (tests only): clears the once-guard and restores the default no-op adapter. */
export function resetAnalytics(): void {
  initialized = false;
  initializer = defaultInitializer;
  capturer = defaultCapturer;
  consentApplier = defaultConsentApplier;
}

/** Options for {@link initAnalytics}; both default to the production sources. */
export interface InitAnalyticsOptions {
  storage?: Storage;
  env?: AnalyticsEnv;
}

/**
 * Boot analytics IFF consent is granted AND a key is configured — at most once per session.
 *
 * Returns `true` exactly on the call that actually initialises (so callers/tests can assert "init
 * happened once"); returns `false` (and touches nothing) before consent, after a denial, when no key
 * is configured, or on any call after the first successful init. This is the privacy guarantee: no
 * analytics initialisation can fire before an explicit opt-in.
 */
export function initAnalytics({
  storage = localStorage,
  env = import.meta.env,
}: InitAnalyticsOptions = {}): boolean {
  if (initialized) {
    return false;
  }
  if (readConsent(storage) !== 'granted') {
    return false;
  }
  const key = analyticsKey(env);
  if (key === undefined) {
    return false;
  }
  initializer(key);
  initialized = true;
  return true;
}

/**
 * Send a product-analytics event — but ONLY while the SDK is booted AND consent is granted.
 *
 * This is the capture-side privacy gate (mirroring {@link initAnalytics} for boot): an event is
 * dropped before opt-in, when no key configured the SDK (so it never booted), and immediately after
 * an opt-out (the persisted decision flips to `denied`), independently of the SDK's own opt-out. So
 * no event can be sent without a live, granted consent. Properties MUST be free of PII.
 */
export function captureAnalytics(
  event: string,
  properties?: Record<string, unknown>,
  { storage = localStorage }: { storage?: Storage } = {},
): void {
  if (!initialized) {
    return;
  }
  if (readConsent(storage) !== 'granted') {
    return;
  }
  capturer(event, properties);
}

/**
 * Reconcile the analytics SDK with a consent decision — call this on every decision change.
 *
 * On `granted` it boots the SDK on the first opt-in ({@link initAnalytics}, key-gated + idempotent)
 * and resumes capturing on an already-booted SDK (re-opt-in after a prior opt-out). On `denied` it
 * pauses capturing on the live SDK (`opt_out`). `null` (undecided) is a no-op — nothing loads until
 * an explicit choice. The applier is a no-op when the SDK never booted, so this is always safe.
 */
export function applyAnalyticsConsent(
  decision: AnalyticsDecision | null,
  options: InitAnalyticsOptions = {},
): void {
  if (decision === 'granted') {
    initAnalytics(options);
    consentApplier(true);
  } else if (decision === 'denied') {
    consentApplier(false);
  }
}
