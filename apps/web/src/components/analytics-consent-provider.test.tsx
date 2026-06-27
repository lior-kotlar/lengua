import { render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useAnalyticsConsent } from '@/components/analytics-consent-context';
import { AnalyticsConsentProvider } from '@/components/analytics-consent-provider';
import {
  ANALYTICS_CONSENT_KEY,
  resetAnalytics,
  setAnalyticsConsentApplier,
  setAnalyticsInitializer,
} from '@/lib/analytics';

/** A tiny consumer that surfaces the decision + drives grant/deny. */
function Consumer() {
  const { decision, grant, deny } = useAnalyticsConsent();
  return (
    <div>
      <span data-testid="decision">{decision ?? 'undecided'}</span>
      <button onClick={grant}>grant</button>
      <button onClick={deny}>deny</button>
    </div>
  );
}

function renderProvider() {
  return render(
    <AnalyticsConsentProvider>
      <Consumer />
    </AnalyticsConsentProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  resetAnalytics();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('AnalyticsConsentProvider', () => {
  it('starts undecided and does not boot analytics', () => {
    vi.stubEnv('VITE_POSTHOG_KEY', 'phc_test');
    const init = vi.fn();
    setAnalyticsInitializer(init);

    renderProvider();

    expect(screen.getByTestId('decision')).toHaveTextContent('undecided');
    expect(init).not.toHaveBeenCalled();
  });

  it('granting persists consent and boots analytics exactly once', async () => {
    vi.stubEnv('VITE_POSTHOG_KEY', 'phc_test');
    const user = userEvent.setup();
    const init = vi.fn();
    setAnalyticsInitializer(init);

    renderProvider();
    await user.click(screen.getByRole('button', { name: 'grant' }));

    expect(screen.getByTestId('decision')).toHaveTextContent('granted');
    expect(localStorage.getItem(ANALYTICS_CONSENT_KEY)).toBe('granted');
    expect(init).toHaveBeenCalledTimes(1);
    expect(init).toHaveBeenCalledWith('phc_test');
  });

  it('denying persists the refusal and never boots analytics', async () => {
    vi.stubEnv('VITE_POSTHOG_KEY', 'phc_test');
    const user = userEvent.setup();
    const init = vi.fn();
    setAnalyticsInitializer(init);

    renderProvider();
    await user.click(screen.getByRole('button', { name: 'deny' }));

    expect(screen.getByTestId('decision')).toHaveTextContent('denied');
    expect(localStorage.getItem(ANALYTICS_CONSENT_KEY)).toBe('denied');
    expect(init).not.toHaveBeenCalled();
  });

  it('boots analytics on mount for a returning user who already granted', () => {
    vi.stubEnv('VITE_POSTHOG_KEY', 'phc_test');
    localStorage.setItem(ANALYTICS_CONSENT_KEY, 'granted');
    const init = vi.fn();
    setAnalyticsInitializer(init);

    renderProvider();

    expect(screen.getByTestId('decision')).toHaveTextContent('granted');
    expect(init).toHaveBeenCalledTimes(1);
  });

  it('applies opt-in on grant and opt-out on deny to the live SDK', async () => {
    vi.stubEnv('VITE_POSTHOG_KEY', 'phc_test');
    const user = userEvent.setup();
    const applier = vi.fn();
    setAnalyticsConsentApplier(applier);

    renderProvider();
    // Undecided on mount → the SDK is neither resumed nor paused.
    expect(applier).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'grant' }));
    expect(applier).toHaveBeenLastCalledWith(true);

    await user.click(screen.getByRole('button', { name: 'deny' }));
    expect(applier).toHaveBeenLastCalledWith(false);
  });

  it('resumes the live SDK on mount for a returning opted-in user', () => {
    vi.stubEnv('VITE_POSTHOG_KEY', 'phc_test');
    localStorage.setItem(ANALYTICS_CONSENT_KEY, 'granted');
    const applier = vi.fn();
    setAnalyticsConsentApplier(applier);

    renderProvider();

    expect(applier).toHaveBeenCalledWith(true);
  });

  it('throws when the hook is used outside the provider', () => {
    expect(() => renderHook(() => useAnalyticsConsent())).toThrowError(
      /within an <AnalyticsConsentProvider>/,
    );
  });
});
