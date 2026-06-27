import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { AnalyticsConsentProvider } from '@/components/analytics-consent-provider';
import { AnalyticsConsentToggle } from '@/components/analytics-consent-toggle';
import { ANALYTICS_CONSENT_KEY, resetAnalytics } from '@/lib/analytics';

function renderToggle() {
  return render(
    <AnalyticsConsentProvider>
      <AnalyticsConsentToggle />
    </AnalyticsConsentProvider>,
  );
}

function switchEl() {
  return screen.getByRole('switch', {
    name: 'Share anonymous usage analytics',
  });
}

beforeEach(() => {
  localStorage.clear();
  resetAnalytics();
});

describe('AnalyticsConsentToggle', () => {
  it('starts OFF when undecided', () => {
    renderToggle();
    expect(switchEl()).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByText('Off')).toBeInTheDocument();
  });

  it('turning it on grants + persists consent', async () => {
    const user = userEvent.setup();
    renderToggle();

    await user.click(switchEl());

    expect(switchEl()).toHaveAttribute('aria-checked', 'true');
    expect(localStorage.getItem(ANALYTICS_CONSENT_KEY)).toBe('granted');
    expect(screen.getByText('On — thank you!')).toBeInTheDocument();
  });

  it('shows ON for a returning opted-in user and turning it off denies + persists', async () => {
    const user = userEvent.setup();
    localStorage.setItem(ANALYTICS_CONSENT_KEY, 'granted');
    renderToggle();

    expect(switchEl()).toHaveAttribute('aria-checked', 'true');

    await user.click(switchEl());

    expect(switchEl()).toHaveAttribute('aria-checked', 'false');
    expect(localStorage.getItem(ANALYTICS_CONSENT_KEY)).toBe('denied');
  });
});
