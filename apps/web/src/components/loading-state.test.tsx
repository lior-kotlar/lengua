import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { LoadingState } from '@/components/loading-state';

describe('LoadingState', () => {
  it('renders an accessible skeleton with the default label', () => {
    render(<LoadingState />);
    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('data-testid', 'loading-skeleton');
    expect(status).toHaveAttribute('aria-busy', 'true');
    // The default label is present (visually-hidden) for screen readers.
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });

  it('renders the supplied label for screen readers', () => {
    render(<LoadingState label="Loading your due cards…" />);
    expect(screen.getByText('Loading your due cards…')).toBeInTheDocument();
  });

  it('applies an extra className', () => {
    render(<LoadingState className="mt-4" />);
    expect(screen.getByTestId('loading-skeleton')).toHaveClass('mt-4');
  });
});
