/**
 * Theme context + hook (kept separate from the provider component so the module exports no mix of
 * components and non-components — keeps react-refresh / fast-refresh happy).
 */
import { createContext, useContext } from 'react';

export type Theme = 'light' | 'dark' | 'system';

export interface ThemeContextValue {
  /** The user's chosen theme (may be `system`). */
  theme: Theme;
  /** Persist + apply a new theme choice. */
  setTheme: (theme: Theme) => void;
}

export const ThemeContext = createContext<ThemeContextValue | undefined>(
  undefined,
);

/** localStorage key the persisted theme choice is stored under. */
export const THEME_STORAGE_KEY = 'lengua-theme';

/** Access the current theme + setter. Throws if used outside a `<ThemeProvider>`. */
export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (ctx === undefined) {
    throw new Error('useTheme must be used within a <ThemeProvider>');
  }
  return ctx;
}
