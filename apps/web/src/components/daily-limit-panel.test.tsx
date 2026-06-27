import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DailyLimitPanel } from '@/components/daily-limit-panel';
import { ApiError } from '@/lib/api-client';

describe('DailyLimitPanel', () => {
  it('renders the friendly panel when no error is passed (caller pre-gated)', () => {
    render(<DailyLimitPanel />);
    expect(screen.getByTestId('daily-limit-panel')).toBeInTheDocument();
    expect(screen.getByText('Daily limit reached')).toBeInTheDocument();
    expect(screen.getByText(/try again\s+tomorrow/i)).toBeInTheDocument();
  });

  it('renders for the quota-429 daily-limit error shapes', () => {
    const { rerender } = render(
      <DailyLimitPanel
        error={
          new ApiError({ status: 429, code: 'daily_cap_reached', message: 'x' })
        }
      />,
    );
    expect(screen.getByTestId('daily-limit-panel')).toBeInTheDocument();

    rerender(
      <DailyLimitPanel
        error={
          new ApiError({
            status: 429,
            code: 'daily_limit_reached',
            message: 'x',
          })
        }
      />,
    );
    expect(screen.getByTestId('daily-limit-panel')).toBeInTheDocument();
  });

  it('renders nothing for a non-daily-limit error shape', () => {
    const { container } = render(
      <DailyLimitPanel
        error={new ApiError({ status: 500, message: 'kaboom' })}
      />,
    );
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId('daily-limit-panel')).not.toBeInTheDocument();
  });
});
