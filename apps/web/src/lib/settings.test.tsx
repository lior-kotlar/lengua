import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { schemaLimits } from 'api-types';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock only `getApiClient`; keep the real `unwrap`/`ApiError` so the typed result path is exercised.
const { get, put } = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, getApiClient: () => ({ GET: get, PUT: put }) };
});

import {
  DAILY_NEW_LIMIT_KEY,
  DAILY_TOTAL_LIMIT_KEY,
  DISCOVER_COUNT_KEY,
  initialSettingValue,
  SETTINGS_FIELDS,
  settingsKey,
  useSettingsQuery,
  useUpdateSettings,
  validateSettingValue,
  type SettingsFieldDef,
} from '@/lib/settings';

function ok<T>(data: T, status = 200) {
  return Promise.resolve({
    data,
    error: undefined,
    response: new Response(null, { status }),
  });
}

function makeWrapper(
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  }),
) {
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { Wrapper, queryClient };
}

function field(key: string): SettingsFieldDef {
  const found = SETTINGS_FIELDS.find((f) => f.key === key);
  if (found === undefined) {
    throw new Error(`no settings field for ${key}`);
  }
  return found;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('settings constants', () => {
  it('exposes the known keys and a stable query key', () => {
    expect(DISCOVER_COUNT_KEY).toBe('discover_count');
    expect(DAILY_NEW_LIMIT_KEY).toBe('daily_new_limit');
    expect(DAILY_TOTAL_LIMIT_KEY).toBe('daily_total_limit');
    expect(settingsKey()).toEqual(['settings']);
  });
});

describe('SETTINGS_FIELDS', () => {
  it('lists the three editable settings in order with sane bounds', () => {
    expect(SETTINGS_FIELDS.map((f) => f.key)).toEqual([
      DAILY_NEW_LIMIT_KEY,
      DAILY_TOTAL_LIMIT_KEY,
      DISCOVER_COUNT_KEY,
    ]);
    expect(field(DAILY_NEW_LIMIT_KEY)).toMatchObject({ min: 1, max: 100 });
    expect(field(DAILY_TOTAL_LIMIT_KEY)).toMatchObject({ min: 1, max: 500 });
  });

  it('reads the discover-count bounds from the OpenAPI schema (not hard-coded)', () => {
    expect(field(DISCOVER_COUNT_KEY)).toMatchObject({
      min: schemaLimits.discoverCountMin,
      max: schemaLimits.discoverCountMax,
      fallback: schemaLimits.discoverCountDefault,
    });
  });
});

describe('validateSettingValue', () => {
  const newCards = field(DAILY_NEW_LIMIT_KEY); // 1..100

  it('rejects a blank value', () => {
    expect(validateSettingValue(newCards, '')).toBe('Enter a value.');
    expect(validateSettingValue(newCards, '   ')).toBe('Enter a value.');
  });

  it('rejects a non-integer value', () => {
    expect(validateSettingValue(newCards, 'abc')).toBe('Enter a whole number.');
    expect(validateSettingValue(newCards, '1.5')).toBe('Enter a whole number.');
    expect(validateSettingValue(newCards, '-1')).toBe('Enter a whole number.');
  });

  it('rejects a value outside the bounds', () => {
    expect(validateSettingValue(newCards, '0')).toBe(
      'Must be between 1 and 100.',
    );
    expect(validateSettingValue(newCards, '101')).toBe(
      'Must be between 1 and 100.',
    );
  });

  it('accepts a whole number within the bounds (inclusive ends)', () => {
    expect(validateSettingValue(newCards, '1')).toBeNull();
    expect(validateSettingValue(newCards, '100')).toBeNull();
    expect(validateSettingValue(newCards, ' 42 ')).toBeNull();
  });

  it('uses each field’s own bounds in the message', () => {
    expect(validateSettingValue(field(DAILY_TOTAL_LIMIT_KEY), '600')).toBe(
      'Must be between 1 and 500.',
    );
    const discover = field(DISCOVER_COUNT_KEY);
    expect(validateSettingValue(discover, String(discover.max + 1))).toBe(
      `Must be between ${discover.min} and ${discover.max}.`,
    );
  });
});

describe('initialSettingValue', () => {
  const newCards = field(DAILY_NEW_LIMIT_KEY); // fallback 10

  it('falls back to the field default when settings are absent or unset', () => {
    expect(initialSettingValue(undefined, newCards)).toBe('10');
    expect(initialSettingValue({ values: {} }, newCards)).toBe('10');
    expect(
      initialSettingValue(
        { values: { [DAILY_NEW_LIMIT_KEY]: null } },
        newCards,
      ),
    ).toBe('10');
    expect(
      initialSettingValue(
        { values: { [DAILY_NEW_LIMIT_KEY]: '  ' } },
        newCards,
      ),
    ).toBe('10');
  });

  it('uses the saved value (trimmed) when present', () => {
    expect(
      initialSettingValue(
        { values: { [DAILY_NEW_LIMIT_KEY]: '25' } },
        newCards,
      ),
    ).toBe('25');
    expect(
      initialSettingValue(
        { values: { [DAILY_NEW_LIMIT_KEY]: ' 25 ' } },
        newCards,
      ),
    ).toBe('25');
  });
});

describe('useSettingsQuery', () => {
  it('GETs /settings and returns the values map', async () => {
    get.mockReturnValue(ok({ values: { discover_count: '7' } }));
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useSettingsQuery(), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(get).toHaveBeenCalledWith('/settings');
    expect(result.current.data).toEqual({ values: { discover_count: '7' } });
  });
});

describe('useUpdateSettings', () => {
  it('PUTs /settings with the values and writes the result into the cache', async () => {
    const updated = {
      values: { daily_new_limit: '15', daily_total_limit: '60' },
    };
    put.mockReturnValue(ok(updated));
    const { Wrapper, queryClient } = makeWrapper();
    const { result } = renderHook(() => useUpdateSettings(), {
      wrapper: Wrapper,
    });

    await result.current.mutateAsync({
      daily_new_limit: '15',
      daily_total_limit: '60',
    });

    expect(put).toHaveBeenCalledWith('/settings', {
      body: { values: { daily_new_limit: '15', daily_total_limit: '60' } },
    });
    // The authoritative server map is written straight into the settings query cache (refetch-free).
    expect(queryClient.getQueryData(settingsKey())).toEqual(updated);
  });
});
