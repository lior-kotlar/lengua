/**
 * Activation-funnel analytics events (group 5.9.2): `signup -> add language -> first generate ->
 * first review`.
 *
 * Each helper fires one named event through {@link captureAnalytics}, which only forwards it while
 * analytics is booted AND consent is granted — so these are no-ops before opt-in / after opt-out and
 * in every dev/CI/E2E build (no `VITE_POSTHOG_KEY`). The PostHog funnel (5.9.3, owner/live) derives
 * "first generate" / "first review" from the FIRST occurrence per user, so these fire on every
 * occurrence (which also powers the reviews/day insight).
 *
 * PII RULE: event properties carry NO personal data — never an email, name, the typed words, or any
 * free text. Only coarse, non-identifying signals (a language code, a count, a 1..4 rating). This is
 * asserted in `analytics-events.test.ts`.
 */
import { captureAnalytics } from '@/lib/analytics';

/** The four activation-funnel event names (the funnel steps, in order). */
export const ANALYTICS_EVENTS = {
  signup: 'signup',
  languageAdded: 'language_added',
  generate: 'generate',
  review: 'review',
} as const;

/** Funnel step 1 — a new account was created. `method` is the sign-up method (no PII). */
export function trackSignup(method: 'email' = 'email'): void {
  captureAnalytics(ANALYTICS_EVENTS.signup, { method });
}

/**
 * Funnel step 2 — a language was added. `code` is the (non-PII) language code, e.g. `"es"`, or
 * `null` when none was given; `curated` records whether it came from the curated picker (issue #95)
 * vs the custom/experimental path — a coarse, non-identifying signal. The display name is
 * intentionally NOT sent.
 */
export function trackLanguageAdded(
  code: string | null,
  curated: boolean,
): void {
  captureAnalytics(ANALYTICS_EVENTS.languageAdded, { code, curated });
}

/**
 * Funnel step 3 — sentences were generated. Only the COUNT of input words is sent, never the words
 * themselves (they are user content).
 */
export function trackGenerate(wordCount: number): void {
  captureAnalytics(ANALYTICS_EVENTS.generate, { word_count: wordCount });
}

/** Funnel step 4 — a card was reviewed. `rating` is the FSRS grade (1..4), no PII. */
export function trackReview(rating: number): void {
  captureAnalytics(ANALYTICS_EVENTS.review, { rating });
}
