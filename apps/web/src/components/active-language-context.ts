/**
 * Active-language context + `useActiveLanguage()` hook.
 *
 * Kept separate from the `<ActiveLanguageProvider>` component (the `auth-context` / `use-theme`
 * pattern) so this module exports no mix of components and non-components (react-refresh friendly)
 * and screens can import the hook without pulling in the provider.
 *
 * The "active language" is the one every authenticated screen scopes to (Generate / Review /
 * Discover / the CEFR panel). The selection is persisted per user so it survives reloads.
 */
import { createContext, useContext } from 'react';

import type { LanguageOut } from '@/lib/languages';

export interface ActiveLanguageState {
  /** The user's languages (empty while loading or when none exist). */
  languages: LanguageOut[];
  /** The id of the active language, or `null` when the user has none. */
  activeLanguageId: number | null;
  /** The active language object, or `null` when none is selected. */
  activeLanguage: LanguageOut | null;
  /** Select a language as active (persisted per user). */
  setActiveLanguageId: (id: number) => void;
  /** True while the language list is loading for the first time. */
  isLoading: boolean;
  /** True when the language list failed to load. */
  isError: boolean;
}

export const ActiveLanguageContext = createContext<
  ActiveLanguageState | undefined
>(undefined);

/** Access the active-language state. Throws if used outside an `<ActiveLanguageProvider>`. */
export function useActiveLanguage(): ActiveLanguageState {
  const ctx = useContext(ActiveLanguageContext);
  if (ctx === undefined) {
    throw new Error(
      'useActiveLanguage must be used within an <ActiveLanguageProvider>',
    );
  }
  return ctx;
}

/** localStorage key for a given user's persisted active-language selection. */
export function activeLanguageStorageKey(userId: string): string {
  return `lengua.active-language:${userId}`;
}
