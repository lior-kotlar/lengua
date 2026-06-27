/**
 * Analytics-consent context + `useAnalyticsConsent()` hook (group 4.10.3).
 *
 * Kept separate from the `<AnalyticsConsentProvider>` component (the `auth-context` /
 * `active-language-context` pattern) so this module exports no mix of components and non-components
 * (react-refresh friendly) and the banner can import the hook without pulling in the provider.
 */
import { createContext, useContext } from 'react';

import type { AnalyticsDecision } from '@/lib/analytics';

export interface AnalyticsConsentState {
  /** The user's decision, or `null` when undecided — which is when the consent banner shows. */
  decision: AnalyticsDecision | null;
  /** Opt in: persist consent and boot analytics (if a key is configured). */
  grant: () => void;
  /** Opt out: persist the refusal. Nothing analytics-related ever loads. */
  deny: () => void;
}

export const AnalyticsConsentContext = createContext<
  AnalyticsConsentState | undefined
>(undefined);

/** Access the analytics-consent state. Throws if used outside an `<AnalyticsConsentProvider>`. */
export function useAnalyticsConsent(): AnalyticsConsentState {
  const ctx = useContext(AnalyticsConsentContext);
  if (ctx === undefined) {
    throw new Error(
      'useAnalyticsConsent must be used within an <AnalyticsConsentProvider>',
    );
  }
  return ctx;
}
