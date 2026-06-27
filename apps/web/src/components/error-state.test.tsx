import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ErrorState } from '@/components/error-state';

describe('ErrorState', () => {
  it('renders the default generic error with no retry button', () => {
    render(<ErrorState />);
    const alert = screen.getByRole('alert');
    expect(alert).toHaveAttribute('data-testid', 'error-state');
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText('Please try again.')).toBeInTheDocument();
    // No onRetry → no button.
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('renders a custom title + description', () => {
    render(
      <ErrorState
        title="Couldn't load your cards"
        description="Something went wrong fetching your due batch."
      />,
    );
    expect(screen.getByText("Couldn't load your cards")).toBeInTheDocument();
    expect(
      screen.getByText('Something went wrong fetching your due batch.'),
    ).toBeInTheDocument();
  });

  it('renders a retry button that calls onRetry', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<ErrorState onRetry={onRetry} retryLabel="Reload" />);
    const button = screen.getByRole('button', { name: /reload/i });
    await user.click(button);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
