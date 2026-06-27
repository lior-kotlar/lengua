/**
 * Vowel-marks display preference context (task 4.9.3).
 *
 * Whether to render the harakat / nikkud that vowelized languages carry, or strip them for a
 * bare-consonant reading. A reading preference, persisted on the device like the theme (a single
 * global localStorage key — not per-language), and shown only for vowelized languages.
 *
 * Kept separate from the `<VowelMarksProvider>` component (the `use-theme` / `auth-context` pattern)
 * so this module mixes no components with non-components (react-refresh friendly) and consumers can
 * import the hook without pulling in the provider.
 */
import { createContext, useContext } from 'react';

/** localStorage key for the persisted "show vowel marks" choice (device-global, like the theme). */
export const VOWEL_MARKS_STORAGE_KEY = 'lengua.vowel-marks';

export interface VowelMarksState {
  /** Whether harakat / nikkud are shown (`true`) or stripped from displayed text (`false`). */
  showVowels: boolean;
  /** Set (and persist) the preference. */
  setShowVowels: (show: boolean) => void;
}

export const VowelMarksContext = createContext<VowelMarksState | undefined>(
  undefined,
);

/** Access the vowel-marks preference. Throws if used outside a `<VowelMarksProvider>`. */
export function useVowelMarks(): VowelMarksState {
  const ctx = useContext(VowelMarksContext);
  if (ctx === undefined) {
    throw new Error('useVowelMarks must be used within a <VowelMarksProvider>');
  }
  return ctx;
}
