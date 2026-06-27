import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useAuth } from '@/components/auth-context';

describe('useAuth', () => {
  it('throws when used outside an AuthProvider', () => {
    expect(() => renderHook(() => useAuth())).toThrowError(
      /within an <AuthProvider>/,
    );
  });
});
