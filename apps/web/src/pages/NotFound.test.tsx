import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import NotFound from '@/pages/NotFound';

function renderNotFound() {
  return render(
    <MemoryRouter>
      <NotFound />
    </MemoryRouter>,
  );
}

describe('NotFound', () => {
  it('renders the tinted 404 numeral and a message', () => {
    renderNotFound();
    expect(screen.getByText('404')).toBeInTheDocument();
    expect(screen.getByText(/could not be found/i)).toBeInTheDocument();
  });

  it('links back to the dashboard with a filled pill', () => {
    renderNotFound();
    expect(screen.getByRole('link', { name: 'Dashboard' })).toHaveAttribute(
      'href',
      '/',
    );
  });

  it('adds no heading (EmptyState skin — this terminal page uses <p>s)', () => {
    renderNotFound();
    expect(screen.queryByRole('heading')).not.toBeInTheDocument();
  });
});
