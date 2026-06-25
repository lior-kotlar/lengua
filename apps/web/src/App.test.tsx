import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import App from '@/App';

describe('App', () => {
  it('renders the Home route with the shadcn sample component at /', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('heading', { name: /lengua/i }),
    ).toBeInTheDocument();

    const button = screen.getByTestId('cta-button');
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent('Get started');
    expect(button).toHaveClass('bg-primary');
  });
});
