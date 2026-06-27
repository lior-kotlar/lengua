/**
 * PostHog analytics adapter (group 5.9.1) — the concrete, EU-hosted PostHog implementation behind
 * the provider-agnostic consent seam in `lib/analytics.ts`.
 *
 * Privacy contract (enforced by the seam + the options below):
 *  - `posthog-js` is loaded with a LAZY `import()`, so it is code-split into its own chunk and never
 *    weighs down the main bundle. It loads only when the seam actually boots analytics — i.e. after
 *    an explicit opt-in AND with `VITE_POSTHOG_KEY` configured. Dev/CI/E2E ship no key, so nothing
 *    is ever fetched or sent there (the existing `e2e/consent.spec.ts` asserts zero analytics calls).
 *  - the EU ingestion host keeps data in the EU;
 *  - autocapture / pageview / pageleave / session recording are OFF, so the ONLY events sent are the
 *    explicit, reviewed, PII-free funnel events (group 5.9.2) — no incidental capture of input
 *    values or URLs that could carry personal data;
 *  - `person_profiles: 'identified_only'` keeps users anonymous (we never call `identify`).
 *
 * `registerPostHogAnalytics()` wires these into the seam at app boot (from `main.tsx`).
 */
import type { PostHog, PostHogConfig } from 'posthog-js';

import {
  setAnalyticsCapturer,
  setAnalyticsConsentApplier,
  setAnalyticsInitializer,
} from '@/lib/analytics';

/** PostHog's EU-region ingestion host — keeps captured data in the EU. */
export const POSTHOG_EU_HOST = 'https://eu.i.posthog.com';

/**
 * Privacy-forward PostHog init options. Everything that could incidentally capture personal data is
 * disabled; only the explicit, PII-free events we send (5.9.2) reach PostHog.
 */
export const POSTHOG_OPTIONS: Partial<PostHogConfig> = {
  api_host: POSTHOG_EU_HOST,
  // No incidental capture — only our explicit, reviewed events are sent.
  autocapture: false,
  capture_pageview: false,
  capture_pageleave: false,
  disable_session_recording: true,
  // Keep users anonymous: we never call posthog.identify(), so no person profile is created.
  person_profiles: 'identified_only',
  persistence: 'localStorage',
};

/**
 * The loaded PostHog instance, as a promise (the import is async). `null` until the seam boots
 * analytics. Every adapter call chains off this one promise, so events fired during load are sent in
 * order once it resolves; calls before any boot are dropped (the SDK never loaded).
 */
let instance: Promise<PostHog> | null = null;

/** Boot PostHog with the project key (registered as the seam initializer; called at most once). */
export function initPostHog(key: string): void {
  instance = import('posthog-js').then(({ default: posthog }) => {
    posthog.init(key, POSTHOG_OPTIONS);
    return posthog;
  });
}

/** Forward an event to PostHog once loaded; a no-op before boot. */
export function capturePostHog(
  event: string,
  properties?: Record<string, unknown>,
): void {
  if (instance === null) {
    return;
  }
  void instance.then((posthog) => posthog.capture(event, properties));
}

/** Resume (opt-in) or pause (opt-out) capturing on the live SDK; a no-op before boot. */
export function setPostHogConsent(granted: boolean): void {
  if (instance === null) {
    return;
  }
  void instance.then((posthog) => {
    if (granted) {
      posthog.opt_in_capturing();
    } else {
      posthog.opt_out_capturing();
    }
  });
}

/** Register the PostHog adapter with the consent seam. Call once at app boot (`main.tsx`). */
export function registerPostHogAnalytics(): void {
  setAnalyticsInitializer(initPostHog);
  setAnalyticsCapturer(capturePostHog);
  setAnalyticsConsentApplier(setPostHogConsent);
}

/** Reset the loaded-instance reference (tests only), so each test starts from "not booted". */
export function resetPostHogForTests(): void {
  instance = null;
}
