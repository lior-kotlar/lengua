import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import Privacy from '@/pages/Privacy';

function renderPrivacy() {
  return render(
    <MemoryRouter>
      <Privacy />
    </MemoryRouter>,
  );
}

describe('Privacy policy page', () => {
  it('renders the policy heading and the required disclosures', () => {
    renderPrivacy();
    expect(
      screen.getByRole('heading', { level: 1, name: /privacy policy/i }),
    ).toBeInTheDocument();
    // Store-required disclosures: Supabase (EU) store + the Gemini LLM provider.
    expect(
      screen.getByRole('heading', { name: /Supabase/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Google Gemini/i)).toBeInTheDocument();
  });

  it('links to the contact email and the account-deletion form', () => {
    renderPrivacy();
    const mailto = screen.getAllByRole('link', {
      name: /privacy@lengua\.app/i,
    });
    expect(mailto.length).toBeGreaterThan(0);
    expect(mailto[0]).toHaveAttribute('href', 'mailto:privacy@lengua.app');
    expect(
      screen.getByRole('link', { name: /account-deletion form/i }),
    ).toHaveAttribute('href', '/delete-account');
  });
});
