import { render, screen } from '@testing-library/react';
import { CheckCircle2 } from 'lucide-react';
import { describe, expect, it } from 'vitest';

import { EmptyState } from '@/components/empty-state';

describe('EmptyState', () => {
  it('renders just the title when only a title is given', () => {
    render(<EmptyState title="Nothing here" />);
    const card = screen.getByTestId('empty-state');
    expect(card).toBeInTheDocument();
    expect(screen.getByText('Nothing here')).toBeInTheDocument();
    // No action region (children) is rendered.
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    // Neutral tone: no success accent.
    expect(card).not.toHaveClass('border-green-500/50');
  });

  it('renders a description and action children when provided', () => {
    render(
      <EmptyState
        title="Add a language first"
        description="You need a language."
      >
        <button>Add a language</button>
      </EmptyState>,
    );
    expect(screen.getByText('You need a language.')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Add a language' }),
    ).toBeInTheDocument();
  });

  it('renders the success tone with an icon (celebratory variant)', () => {
    render(
      <EmptyState
        tone="success"
        icon={CheckCircle2}
        title="All caught up"
        description="Nothing due."
      />,
    );
    const card = screen.getByTestId('empty-state');
    expect(card).toHaveClass('border-green-500/50');
    // The icon renders (aria-hidden) — it is the only svg in the header.
    expect(card.querySelector('svg')).not.toBeNull();
  });

  it('renders an icon with the neutral tone by default', () => {
    render(<EmptyState icon={CheckCircle2} title="Pick something" />);
    const card = screen.getByTestId('empty-state');
    expect(card).not.toHaveClass('border-green-500/50');
    // Default tone → the icon uses the muted (not success) colour.
    expect(card.querySelector('svg')).toHaveClass('text-muted-foreground');
  });
});
