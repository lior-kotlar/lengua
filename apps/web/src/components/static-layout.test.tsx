import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/components/theme-toggle', () => ({
  ThemeToggle: () => <button type="button">theme</button>,
}));

import { StaticLayout } from '@/components/static-layout';

function renderStatic() {
  return render(
    <MemoryRouter initialEntries={['/privacy']}>
      <Routes>
        <Route element={<StaticLayout />}>
          <Route path="/privacy" element={<div>routed content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('StaticLayout', () => {
  it('renders the brand link, routed content, and the footer', () => {
    renderStatic();
    expect(screen.getByRole('link', { name: 'Lengua' })).toHaveAttribute(
      'href',
      '/',
    );
    expect(screen.getByText('routed content')).toBeInTheDocument();
    expect(screen.getByTestId('site-footer')).toBeInTheDocument();
  });
});
