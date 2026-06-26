import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import App from '@/App';
import { ThemeProvider } from '@/components/theme-provider';

function renderAt(path: string) {
  return render(
    <ThemeProvider defaultTheme="light">
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe('App routing', () => {
  it('mounts the Dashboard inside the app shell at /', () => {
    renderAt('/');
    expect(
      screen.getByRole('heading', { name: 'Dashboard' }),
    ).toBeInTheDocument();
    // The authenticated shell exposes the primary nav + the brand.
    expect(
      screen.getByRole('navigation', { name: 'Primary' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Lengua' })).toBeInTheDocument();
  });

  it('mounts the Login screen in the auth shell at /login (no app nav)', () => {
    renderAt('/login');
    expect(
      screen.getByRole('heading', { name: /log in/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('navigation', { name: 'Primary' }),
    ).not.toBeInTheDocument();
  });

  it('mounts the Signup screen at /signup', () => {
    renderAt('/signup');
    expect(
      screen.getByRole('heading', { name: /sign up/i }),
    ).toBeInTheDocument();
  });

  it.each([
    ['/generate', 'Generate'],
    ['/review', 'Review'],
    ['/discover', 'Discover'],
    ['/languages', 'Languages'],
    ['/settings', 'Settings'],
    ['/account', 'Account'],
  ])('mounts the %s screen', (path, heading) => {
    renderAt(path);
    expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument();
  });

  it('renders the 404 screen for an unknown route', () => {
    renderAt('/does-not-exist');
    expect(screen.getByRole('heading', { name: '404' })).toBeInTheDocument();
  });
});
