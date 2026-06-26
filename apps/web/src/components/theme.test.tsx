import { render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '@/components/theme-provider';
import { ThemeToggle } from '@/components/theme-toggle';
import { useTheme } from '@/components/use-theme';

function setSystemPrefersDark(matches: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

const root = document.documentElement;

afterEach(() => {
  root.classList.remove('light', 'dark');
  setSystemPrefersDark(false);
});

describe('ThemeProvider', () => {
  it('applies the light class when system prefers light', () => {
    setSystemPrefersDark(false);
    render(
      <ThemeProvider defaultTheme="system">
        <div />
      </ThemeProvider>,
    );
    expect(root.classList.contains('light')).toBe(true);
    expect(root.classList.contains('dark')).toBe(false);
  });

  it('applies the dark class when system prefers dark', () => {
    setSystemPrefersDark(true);
    render(
      <ThemeProvider defaultTheme="system">
        <div />
      </ThemeProvider>,
    );
    expect(root.classList.contains('dark')).toBe(true);
  });

  it('falls back to the default when the stored value is invalid', () => {
    localStorage.setItem('lengua-theme', 'not-a-theme');
    render(
      <ThemeProvider defaultTheme="light">
        <div />
      </ThemeProvider>,
    );
    expect(root.classList.contains('light')).toBe(true);
  });

  it('reads a persisted theme on (re)mount', () => {
    localStorage.setItem('lengua-theme', 'dark');
    render(
      <ThemeProvider defaultTheme="light">
        <div />
      </ThemeProvider>,
    );
    expect(root.classList.contains('dark')).toBe(true);
  });
});

describe('useTheme', () => {
  it('throws when used outside a ThemeProvider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => renderHook(() => useTheme())).toThrowError(
      /within a <ThemeProvider>/,
    );
    spy.mockRestore();
  });
});

describe('ThemeToggle', () => {
  it('toggles to dark, persists, survives a remount, and toggles back', async () => {
    setSystemPrefersDark(false);
    const user = userEvent.setup();

    const view = render(
      <ThemeProvider defaultTheme="light">
        <ThemeToggle />
      </ThemeProvider>,
    );
    expect(root.classList.contains('light')).toBe(true);

    await user.click(
      screen.getByRole('button', { name: /switch to dark theme/i }),
    );
    expect(root.classList.contains('dark')).toBe(true);
    expect(localStorage.getItem('lengua-theme')).toBe('dark');

    // Survives a remount: the choice is read back from localStorage.
    view.unmount();
    render(
      <ThemeProvider defaultTheme="light">
        <ThemeToggle />
      </ThemeProvider>,
    );
    expect(root.classList.contains('dark')).toBe(true);

    await user.click(
      screen.getByRole('button', { name: /switch to light theme/i }),
    );
    expect(root.classList.contains('light')).toBe(true);
    expect(localStorage.getItem('lengua-theme')).toBe('light');
  });

  it('reflects the resolved system appearance (dark)', () => {
    setSystemPrefersDark(true);
    render(
      <ThemeProvider defaultTheme="system">
        <ThemeToggle />
      </ThemeProvider>,
    );
    expect(
      screen.getByRole('button', { name: /switch to light theme/i }),
    ).toBeInTheDocument();
  });
});
