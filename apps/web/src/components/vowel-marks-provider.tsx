/**
 * Vowel-marks display-preference provider (task 4.9.3).
 *
 * Holds the "show harakat / nikkud" reading preference and persists it to localStorage (a single
 * device-global key, mirroring `ThemeProvider`), defaulting to ON so vowelized languages show their
 * marks until the learner chooses otherwise. Mounted inside `AppLayout`, so every authenticated
 * language screen (Generate / Review / Discover) and the `VowelMarksToggle` share one source of
 * truth; flipping the toggle re-renders the screens, which re-strip their target text.
 */
import { useMemo, useState } from 'react';

import {
  VOWEL_MARKS_STORAGE_KEY,
  VowelMarksContext,
  type VowelMarksState,
} from '@/components/vowel-marks-context';

function readStoredPreference(storageKey: string, fallback: boolean): boolean {
  const stored = localStorage.getItem(storageKey);
  if (stored === 'true') {
    return true;
  }
  if (stored === 'false') {
    return false;
  }
  return fallback;
}

export interface VowelMarksProviderProps {
  children: React.ReactNode;
  /** Preference used when nothing is persisted yet (default: show marks). */
  defaultShowVowels?: boolean;
  /** Override the localStorage key (mainly for tests). */
  storageKey?: string;
}

export function VowelMarksProvider({
  children,
  defaultShowVowels = true,
  storageKey = VOWEL_MARKS_STORAGE_KEY,
}: VowelMarksProviderProps) {
  const [showVowels, setShowVowelsState] = useState<boolean>(() =>
    readStoredPreference(storageKey, defaultShowVowels),
  );

  const value = useMemo<VowelMarksState>(
    () => ({
      showVowels,
      setShowVowels: (next: boolean) => {
        localStorage.setItem(storageKey, String(next));
        setShowVowelsState(next);
      },
    }),
    [showVowels, storageKey],
  );

  return (
    <VowelMarksContext.Provider value={value}>
      {children}
    </VowelMarksContext.Provider>
  );
}
