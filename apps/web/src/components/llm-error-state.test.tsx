import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { LlmErrorState } from '@/components/llm-error-state';
import { ApiError } from '@/lib/api-client';

function apiError(status: number, code: string, retryAfter?: number) {
  return new ApiError({
    status,
    code,
    message: `failed: ${code}`,
    retryAfter,
  });
}

describe('LlmErrorState', () => {
  it('renders the shared daily-limit panel for the per-user cap (daily_cap_reached)', () => {
    render(<LlmErrorState error={apiError(429, 'daily_cap_reached')} />);
    expect(screen.getByTestId('daily-limit-panel')).toBeInTheDocument();
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
  });

  it('renders the shared daily-limit panel for the global kill-switch (daily_limit_reached)', () => {
    render(<LlmErrorState error={apiError(429, 'daily_limit_reached')} />);
    expect(screen.getByTestId('daily-limit-panel')).toBeInTheDocument();
  });

  it('renders a transient server-busy state with the supplied hint', () => {
    render(
      <LlmErrorState
        error={apiError(503, 'server_busy', 3)}
        transientHint="Keep calm and retry."
      />,
    );
    expect(screen.getByText('The server is busy')).toBeInTheDocument();
    expect(screen.getByText('Keep calm and retry.')).toBeInTheDocument();
    expect(screen.queryByTestId('daily-limit-panel')).not.toBeInTheDocument();
  });

  it('renders a transient rate-limited state', () => {
    render(<LlmErrorState error={apiError(429, 'rate_limited', 2)} />);
    expect(screen.getByText('Too many requests')).toBeInTheDocument();
  });

  it('omits the hint paragraph for a transient state when no hint is given', () => {
    const { container } = render(
      <LlmErrorState error={apiError(503, 'server_busy')} />,
    );
    expect(screen.getByText('The server is busy')).toBeInTheDocument();
    // The hint is the only <p> the inline card renders (title/description are <div>s), so with no
    // hint there is none — proving the transient-hint branch short-circuits on `undefined`.
    expect(container.querySelectorAll('p')).toHaveLength(0);
  });

  it('does not show the transient hint for a non-transient (generic) error', () => {
    render(
      <LlmErrorState
        error={apiError(500, 'kaboom')}
        transientHint="should not appear"
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong');
    expect(screen.queryByText('should not appear')).not.toBeInTheDocument();
  });

  it('renders a verify-email state', () => {
    render(<LlmErrorState error={apiError(403, 'email_unverified')} />);
    expect(screen.getByText('Verify your email')).toBeInTheDocument();
  });
});
