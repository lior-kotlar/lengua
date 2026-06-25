import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import Home from '@/pages/Home';

describe('Home', () => {
  it('renders the heading', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<Home />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('heading', { name: /lengua/i }),
    ).toBeInTheDocument();
  });

  it('renders the shadcn Button sample component with Tailwind classes', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<Home />} />
        </Routes>
      </MemoryRouter>,
    );

    const button = screen.getByTestId('cta-button');
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent('Get started');
    // shadcn Button renders a real <button> with its variant utility classes.
    expect(button.tagName).toBe('BUTTON');
    expect(button).toHaveClass('bg-primary');
    expect(button).toHaveClass('inline-flex');
  });
});
