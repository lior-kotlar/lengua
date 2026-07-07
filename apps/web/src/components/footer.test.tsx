import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { Footer } from '@/components/footer';

function renderFooter(className?: string) {
  return render(
    <MemoryRouter>
      <Footer className={className} />
    </MemoryRouter>,
  );
}

describe('Footer', () => {
  it('links to the published Privacy and Support pages', () => {
    renderFooter();
    expect(screen.getByRole('link', { name: 'Privacy' })).toHaveAttribute(
      'href',
      '/privacy',
    );
    expect(screen.getByRole('link', { name: 'Support' })).toHaveAttribute(
      'href',
      '/support',
    );
  });

  it('is a contentinfo landmark and merges an extra className', () => {
    renderFooter('hidden sm:block');
    const footer = screen.getByTestId('site-footer');
    expect(footer.tagName).toBe('FOOTER');
    expect(footer).toHaveClass('hidden');
  });
});
