/**
 * Analytics-consent provider (group 4.10.3).
 *
 * Tracks the persisted analytics decision and exposes `grant()` / `deny()`. Analytics is booted
 * exclusively through {@link initAnalytics} — which no-ops until consent is granted AND a key is
 * configured — so mounting this provider never starts analytics on its own. It boots once the
 * decision is (or, on mount, already was) `granted`; the init is idempotent, so a returning opted-in
 * user boots analytics exactly once and a fresh opt-in boots it exactly once.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  AnalyticsConsentContext,
  type AnalyticsConsentState,
} from '@/components/analytics-consent-context';
import {
  initAnalytics,
  persistConsent,
  readConsent,
  type AnalyticsDecision,
} from '@/lib/analytics';

export interface AnalyticsConsentProviderProps {
  children: React.ReactNode;
}

export function AnalyticsConsentProvider({
  children,
}: AnalyticsConsentProviderProps) {
  const [decision, setDecision] = useState<AnalyticsDecision | null>(() =>
    readConsent(),
  );

  // Boot analytics whenever consent is granted (on mount for a returning user, or right after a
  // fresh opt-in). `initAnalytics` is the single guarded entry point — idempotent + key-gated — so
  // this never double-initialises and never runs before an explicit grant.
  useEffect(() => {
    if (decision === 'granted') {
      initAnalytics();
    }
  }, [decision]);

  const grant = useCallback(() => {
    persistConsent('granted');
    setDecision('granted');
  }, []);

  const deny = useCallback(() => {
    persistConsent('denied');
    setDecision('denied');
  }, []);

  const value = useMemo<AnalyticsConsentState>(
    () => ({ decision, grant, deny }),
    [decision, grant, deny],
  );

  return (
    <AnalyticsConsentContext.Provider value={value}>
      {children}
    </AnalyticsConsentContext.Provider>
  );
}
