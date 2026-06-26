import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PlaceholderScreen } from '@/components/placeholder-screen';

describe('PlaceholderScreen', () => {
  it('renders the title and provided description', () => {
    render(<PlaceholderScreen title="Generate" description="Make sentences" />);
    expect(
      screen.getByRole('heading', { name: 'Generate' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Make sentences')).toBeInTheDocument();
  });

  it('falls back to default copy when no description is given', () => {
    render(<PlaceholderScreen title="Review" />);
    expect(screen.getByText('Coming soon.')).toBeInTheDocument();
  });
});
