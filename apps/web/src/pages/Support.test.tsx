import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import Support from '@/pages/Support';

function renderSupport() {
  return render(
    <MemoryRouter>
      <Support />
    </MemoryRouter>,
  );
}

describe('Support page', () => {
  it('renders the heading and a contact email', () => {
    renderSupport();
    expect(
      screen.getByRole('heading', { level: 1, name: /support/i }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole('link', { name: /privacy@lengua\.app/i })[0],
    ).toHaveAttribute('href', 'mailto:privacy@lengua.app');
  });

  it('links to the Privacy policy and the account-deletion form', () => {
    renderSupport();
    expect(
      screen.getByRole('link', { name: /privacy policy/i }),
    ).toHaveAttribute('href', '/privacy');
    expect(
      screen.getByRole('link', { name: /account-deletion form/i }),
    ).toHaveAttribute('href', '/delete-account');
  });
});
