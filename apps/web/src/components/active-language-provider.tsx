/**
 * Active-language provider (task 4.4.1).
 *
 * Loads the user's languages and tracks which one is "active" — the language every authenticated
 * screen scopes to. The selection is:
 *  - **persisted per user** in localStorage (keyed by user id, so two accounts on one browser don't
 *    clobber each other), and
 *  - **reconciled against the fetched list** every time it changes: an invalid/absent selection
 *    falls back to the first language, and an empty account resolves to `null`.
 *
 * Mounted inside `AppLayout` (behind `RequireAuth`), so it only ever runs for an authenticated user
 * and never fires `GET /languages` on the public auth screens. Because language-scoped queries are
 * keyed by the active id, switching the picker changes those keys and TanStack Query refetches.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  ActiveLanguageContext,
  activeLanguageStorageKey,
  type ActiveLanguageState,
} from '@/components/active-language-context';
import { useAuth } from '@/components/auth-context';
import { useLanguagesQuery } from '@/lib/languages';

export interface ActiveLanguageProviderProps {
  children: React.ReactNode;
}

export function ActiveLanguageProvider({
  children,
}: ActiveLanguageProviderProps) {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const { data: languages, isLoading, isError } = useLanguagesQuery();

  const [activeId, setActiveId] = useState<number | null>(null);

  // Seed the desired selection from storage whenever the user changes. Reconciliation against the
  // fetched list happens in the next effect, so a stale stored id is harmless.
  useEffect(() => {
    if (userId === null) {
      setActiveId(null);
      return;
    }
    const raw = localStorage.getItem(activeLanguageStorageKey(userId));
    setActiveId(raw === null ? null : Number(raw));
  }, [userId]);

  // Reconcile against the fetched list: keep a still-valid selection, otherwise default to the first
  // language (or `null` for an empty account). Runs only when the list changes (not on every active
  // id change), and is a no-op when the current selection is already valid — so no render loop.
  useEffect(() => {
    if (languages === undefined) {
      return;
    }
    setActiveId((current) => {
      if (current !== null && languages.some((l) => l.id === current)) {
        return current;
      }
      return languages[0]?.id ?? null;
    });
  }, [languages]);

  const setActiveLanguageId = useCallback(
    (id: number) => {
      setActiveId(id);
      if (userId !== null) {
        localStorage.setItem(activeLanguageStorageKey(userId), String(id));
      }
    },
    [userId],
  );

  const activeLanguage = useMemo(
    () => languages?.find((l) => l.id === activeId) ?? null,
    [languages, activeId],
  );

  const value = useMemo<ActiveLanguageState>(
    () => ({
      languages: languages ?? [],
      activeLanguageId: activeId,
      activeLanguage,
      setActiveLanguageId,
      isLoading,
      isError,
    }),
    [
      languages,
      activeId,
      activeLanguage,
      setActiveLanguageId,
      isLoading,
      isError,
    ],
  );

  return (
    <ActiveLanguageContext.Provider value={value}>
      {children}
    </ActiveLanguageContext.Provider>
  );
}
