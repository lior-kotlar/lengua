/**
 * Analytics consent seam (group 4.10.3).
 *
 * Product analytics (PostHog is the intended provider, wired fully in Phase 5/8) must NEVER load or
 * collect anything until the user explicitly opts in. This module is the single chokepoint that
 * enforces that contract:
 *
 *  - the decision (`granted` / `denied`) is persisted in localStorage, so the first-run banner is
 *    shown once and never re-prompts after a choice;
 *  - {@link initAnalytics} boots the analytics SDK at most once, and ONLY when consent is granted
 *    AND an analytics key is configured (`VITE_POSTHOG_KEY`). With no key, the choice still persists
 *    and nothing loads — a clean seam behind an env flag, so dev/CI/E2E never ship analytics.
 *
 * The actual PostHog boot is deferred to Phase 5/8; until then the default initializer is a
 * documented no-op. It is kept injectable ({@link setAnalyticsInitializer}) so the "init exactly
 * once, only after consent" contract is unit-testable and so Phase 5/8 can register the real loader
 * without touching this consent logic.
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

/** Boots the analytics SDK with the configured key. Registered by Phase 5/8 (or a test). */
export type AnalyticsInitializer = (key: string) => void;

// Phase 5/8 will register a real initializer that `import('posthog-js')` + `posthog.init(key, …)`.
// Until then this is an intentional no-op: consent still gates it, but nothing actually loads.
function defaultInitializer(): void {
  /* no-op placeholder — Phase 5/8 wires the real PostHog boot here */
}

let initializer: AnalyticsInitializer = defaultInitializer;
let initialized = false;

/** Register the analytics initializer (Phase 5/8 wiring, or a test spy). */
export function setAnalyticsInitializer(fn: AnalyticsInitializer): void {
  initializer = fn;
}

/** Reset the init seam (tests only): clears the once-guard and restores the default initializer. */
export function resetAnalytics(): void {
  initialized = false;
  initializer = defaultInitializer;
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
