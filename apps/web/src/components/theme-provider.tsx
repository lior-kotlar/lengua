/**
 * Light/dark theming via shadcn CSS variables.
 *
 * Applies the resolved theme as a class on `document.documentElement` (`dark` toggles the dark
 * token set in `index.css`), persists the user's choice to localStorage, and supports a `system`
 * mode that follows the OS `prefers-color-scheme`.
 */
import { useEffect, useMemo, useState } from 'react';

import {
  THEME_STORAGE_KEY,
  ThemeContext,
  type Theme,
} from '@/components/use-theme';

function readStoredTheme(storageKey: string, fallback: Theme): Theme {
  const stored = localStorage.getItem(storageKey);
  if (stored === 'light' || stored === 'dark' || stored === 'system') {
    return stored;
  }
  return fallback;
}

function resolveSystemTheme(): 'light' | 'dark' {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light';
}

export interface ThemeProviderProps {
  children: React.ReactNode;
  /** Theme used when nothing is persisted yet. */
  defaultTheme?: Theme;
  /** Override the localStorage key (mainly for tests). */
  storageKey?: string;
}

export function ThemeProvider({
  children,
  defaultTheme = 'system',
  storageKey = THEME_STORAGE_KEY,
}: ThemeProviderProps) {
  const [theme, setThemeState] = useState<Theme>(() =>
    readStoredTheme(storageKey, defaultTheme),
  );

  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove('light', 'dark');
    const applied = theme === 'system' ? resolveSystemTheme() : theme;
    root.classList.add(applied);
  }, [theme]);

  const value = useMemo(
    () => ({
      theme,
      setTheme: (next: Theme) => {
        localStorage.setItem(storageKey, next);
        setThemeState(next);
      },
    }),
    [theme, storageKey],
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}
