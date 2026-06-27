import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { AnalyticsConsentBanner } from '@/components/analytics-consent-banner';
import {
  AnalyticsConsentContext,
  type AnalyticsConsentState,
} from '@/components/analytics-consent-context';

function renderBanner(
  overrides: Partial<AnalyticsConsentState> = {},
): AnalyticsConsentState {
  const value: AnalyticsConsentState = {
    decision: null,
    grant: vi.fn(),
    deny: vi.fn(),
    ...overrides,
  };
  render(
    <AnalyticsConsentContext.Provider value={value}>
      <AnalyticsConsentBanner />
    </AnalyticsConsentContext.Provider>,
  );
  return value;
}

describe('AnalyticsConsentBanner', () => {
  it('shows a labelled region while the decision is undecided', () => {
    renderBanner({ decision: null });
    expect(screen.getByTestId('analytics-consent')).toBeInTheDocument();
    expect(
      screen.getByRole('region', { name: 'Analytics consent' }),
    ).toBeInTheDocument();
  });

  it('calls grant when Accept is clicked (opt-in)', async () => {
    const user = userEvent.setup();
    const value = renderBanner({ decision: null });
    await user.click(screen.getByRole('button', { name: 'Accept' }));
    expect(value.grant).toHaveBeenCalledTimes(1);
    expect(value.deny).not.toHaveBeenCalled();
  });

  it('calls deny when Decline is clicked (opt-out)', async () => {
    const user = userEvent.setup();
    const value = renderBanner({ decision: null });
    await user.click(screen.getByRole('button', { name: 'Decline' }));
    expect(value.deny).toHaveBeenCalledTimes(1);
    expect(value.grant).not.toHaveBeenCalled();
  });

  it('renders nothing once a decision has been made', () => {
    renderBanner({ decision: 'granted' });
    expect(screen.queryByTestId('analytics-consent')).not.toBeInTheDocument();
  });
});
