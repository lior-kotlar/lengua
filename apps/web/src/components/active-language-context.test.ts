import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  activeLanguageStorageKey,
  useActiveLanguage,
} from '@/components/active-language-context';

describe('useActiveLanguage', () => {
  it('throws when used outside an ActiveLanguageProvider', () => {
    expect(() => renderHook(() => useActiveLanguage())).toThrowError(
      /within an <ActiveLanguageProvider>/,
    );
  });
});

describe('activeLanguageStorageKey', () => {
  it('namespaces the persisted selection per user', () => {
    expect(activeLanguageStorageKey('user-1')).toBe(
      'lengua.active-language:user-1',
    );
    expect(activeLanguageStorageKey('user-2')).not.toBe(
      activeLanguageStorageKey('user-1'),
    );
  });
});
