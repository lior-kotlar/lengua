import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  VOWEL_MARKS_STORAGE_KEY,
  useVowelMarks,
} from '@/components/vowel-marks-context';

describe('useVowelMarks', () => {
  it('throws when used outside a VowelMarksProvider', () => {
    expect(() => renderHook(() => useVowelMarks())).toThrowError(
      /within a <VowelMarksProvider>/,
    );
  });
});

describe('VOWEL_MARKS_STORAGE_KEY', () => {
  it('is a stable, namespaced key', () => {
    expect(VOWEL_MARKS_STORAGE_KEY).toBe('lengua.vowel-marks');
  });
});
