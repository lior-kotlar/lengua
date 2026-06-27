import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import {
  VOWEL_MARKS_STORAGE_KEY,
  useVowelMarks,
} from '@/components/vowel-marks-context';
import { VowelMarksProvider } from '@/components/vowel-marks-provider';

function wrapper({ children }: { children: React.ReactNode }) {
  return <VowelMarksProvider>{children}</VowelMarksProvider>;
}

afterEach(() => {
  localStorage.clear();
});

describe('VowelMarksProvider', () => {
  it('defaults to showing vowel marks when nothing is persisted', () => {
    const { result } = renderHook(() => useVowelMarks(), { wrapper });
    expect(result.current.showVowels).toBe(true);
  });

  it('honours a persisted "false" preference', () => {
    localStorage.setItem(VOWEL_MARKS_STORAGE_KEY, 'false');
    const { result } = renderHook(() => useVowelMarks(), { wrapper });
    expect(result.current.showVowels).toBe(false);
  });

  it('honours a persisted "true" preference', () => {
    localStorage.setItem(VOWEL_MARKS_STORAGE_KEY, 'true');
    const { result } = renderHook(() => useVowelMarks(), { wrapper });
    expect(result.current.showVowels).toBe(true);
  });

  it('falls back to the default when the stored value is malformed', () => {
    localStorage.setItem(VOWEL_MARKS_STORAGE_KEY, 'maybe');
    const { result } = renderHook(() => useVowelMarks(), {
      wrapper: ({ children }) => (
        <VowelMarksProvider defaultShowVowels={false}>
          {children}
        </VowelMarksProvider>
      ),
    });
    expect(result.current.showVowels).toBe(false);
  });

  it('persists a change and reads it back on a fresh mount', () => {
    const first = renderHook(() => useVowelMarks(), { wrapper });
    act(() => first.result.current.setShowVowels(false));
    expect(first.result.current.showVowels).toBe(false);
    expect(localStorage.getItem(VOWEL_MARKS_STORAGE_KEY)).toBe('false');
    first.unmount();

    const second = renderHook(() => useVowelMarks(), { wrapper });
    expect(second.result.current.showVowels).toBe(false);
  });

  it('supports a custom storage key', () => {
    localStorage.setItem('custom.vowels', 'false');
    const { result } = renderHook(() => useVowelMarks(), {
      wrapper: ({ children }) => (
        <VowelMarksProvider storageKey="custom.vowels">
          {children}
        </VowelMarksProvider>
      ),
    });
    expect(result.current.showVowels).toBe(false);
  });
});
