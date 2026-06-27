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
  applyAnalyticsConsent,
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

  // Reconcile analytics with the decision on mount and on every change. `applyAnalyticsConsent` is
  // the single guarded entry point: on `granted` it boots once (idempotent + key-gated) and resumes
  // capturing on an already-booted SDK; on `denied` it opts the live SDK out. So a returning opted-in
  // user boots once, a fresh opt-in boots once, and a post-banner toggle in Settings flips capturing
  // on/off — never running before an explicit grant.
  useEffect(() => {
    applyAnalyticsConsent(decision);
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
