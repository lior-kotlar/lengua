import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DailyLimitPanel } from '@/components/daily-limit-panel';
import { ApiError } from '@/lib/api-client';

describe('DailyLimitPanel', () => {
  it('renders the friendly panel when no error is passed (caller pre-gated)', () => {
    render(<DailyLimitPanel />);
    const panel = screen.getByTestId('daily-limit-panel');
    expect(panel).toBeInTheDocument();
    // The orange callout keeps its polite live-region role so it is announced when a call is refused.
    expect(panel).toHaveAttribute('role', 'status');
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

  it('renders nothing for a 429 that is NOT a quota code (tied to the quota shape, not just status)', () => {
    // A 429 rate-limit is NOT the daily-limit panel's concern — the panel is tied to the quota
    // response shape (daily_cap_reached / daily_limit_reached), not merely the 429 status.
    const { container } = render(
      <DailyLimitPanel
        error={
          new ApiError({ status: 429, code: 'rate_limited', message: 'slow' })
        }
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe('DailyLimitPanel — copy adapts to which limit was hit (S19)', () => {
  /** A per-user `daily_cap_reached` 429 carrying the offending `kind` in its body. */
  function capError(kind: string): ApiError {
    return new ApiError({
      status: 429,
      code: 'daily_cap_reached',
      message: 'x',
      body: { code: 'daily_cap_reached', kind },
    });
  }

  it('names the generating action for a generate cap', () => {
    render(<DailyLimitPanel error={capError('generate')} />);
    expect(
      screen.getByText(/daily limit for generating sentences/i),
    ).toBeInTheDocument();
  });

  it('names the discover action for a discover cap (never "generation")', () => {
    render(<DailyLimitPanel error={capError('discover')} />);
    expect(
      screen.getByText(/daily limit for discovering words/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/generation|generating/i),
    ).not.toBeInTheDocument();
  });

  it('frames the global kill-switch as affecting everyone (never "generation")', () => {
    render(
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
    expect(screen.getByText(/daily limit for everyone/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/generation|generating/i),
    ).not.toBeInTheDocument();
  });

  it('falls back to kind-agnostic copy when the kind is unknown or absent', () => {
    // A `daily_cap_reached` with no body (kind unknown) and the pre-gated no-error render both use
    // the neutral copy — never the generate-specific wording.
    const { rerender } = render(
      <DailyLimitPanel
        error={
          new ApiError({ status: 429, code: 'daily_cap_reached', message: 'x' })
        }
      />,
    );
    expect(
      screen.getByText(/you have reached the daily limit\./i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/generation|generating/i),
    ).not.toBeInTheDocument();

    rerender(<DailyLimitPanel />);
    expect(
      screen.getByText(/you have reached the daily limit\./i),
    ).toBeInTheDocument();
  });
});
