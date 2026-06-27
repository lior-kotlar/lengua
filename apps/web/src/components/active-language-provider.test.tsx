import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { Session, User } from '@supabase/supabase-js';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { useLanguagesQuery } = vi.hoisted(() => ({
  useLanguagesQuery: vi.fn(),
}));
vi.mock('@/lib/languages', () => ({ useLanguagesQuery }));

import {
  activeLanguageStorageKey,
  useActiveLanguage,
} from '@/components/active-language-context';
import { ActiveLanguageProvider } from '@/components/active-language-provider';
import { AuthContext, type AuthState } from '@/components/auth-context';

const LANGS = [
  { id: 1, name: 'Spanish', code: 'es', vowelized: false },
  { id: 2, name: 'French', code: 'fr', vowelized: false },
];

const USER_ID = 'user-1';

/** Records the language id each scoped query is keyed by, to prove refetch-on-switch. */
const scopedKeys: Array<number | null> = [];

/** Spy for the languages query's `refetch`, surfaced through the context for the retry path. */
const languagesRefetch = vi.fn();

function Probe() {
  const {
    activeLanguageId,
    activeLanguage,
    languages,
    setActiveLanguageId,
    refetch,
  } = useActiveLanguage();

  useQuery({
    queryKey: ['scoped', activeLanguageId],
    queryFn: () => {
      scopedKeys.push(activeLanguageId);
      return Promise.resolve('data');
    },
    enabled: activeLanguageId !== null,
  });

  return (
    <div>
      <span data-testid="active-id">{activeLanguageId ?? 'none'}</span>
      <span data-testid="active-name">{activeLanguage?.name ?? 'none'}</span>
      {languages.map((language) => (
        <button
          key={language.id}
          onClick={() => setActiveLanguageId(language.id)}
        >
          pick {language.name}
        </button>
      ))}
      <button onClick={refetch}>retry languages</button>
    </div>
  );
}

function renderProvider(userId: string | null = USER_ID) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const authState: AuthState = {
    session: {} as Session,
    user: (userId === null ? null : ({ id: userId } as User)) as User | null,
    loading: false,
  };
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={authState}>
        <ActiveLanguageProvider>
          <Probe />
        </ActiveLanguageProvider>
      </AuthContext.Provider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  scopedKeys.length = 0;
  useLanguagesQuery.mockReturnValue({
    data: LANGS,
    isLoading: false,
    isError: false,
    refetch: languagesRefetch,
  });
});

describe('ActiveLanguageProvider', () => {
  it('defaults the active language to the first one when nothing is stored', async () => {
    renderProvider();
    await waitFor(() =>
      expect(screen.getByTestId('active-id')).toHaveTextContent('1'),
    );
    expect(screen.getByTestId('active-name')).toHaveTextContent('Spanish');
  });

  it('restores a persisted selection from localStorage', async () => {
    localStorage.setItem(activeLanguageStorageKey(USER_ID), '2');
    renderProvider();
    await waitFor(() =>
      expect(screen.getByTestId('active-id')).toHaveTextContent('2'),
    );
    expect(screen.getByTestId('active-name')).toHaveTextContent('French');
  });

  it('falls back to the first language when the stored id is no longer valid', async () => {
    localStorage.setItem(activeLanguageStorageKey(USER_ID), '99');
    renderProvider();
    await waitFor(() =>
      expect(screen.getByTestId('active-id')).toHaveTextContent('1'),
    );
  });

  it('persists the selection and refetches language-scoped queries on switch', async () => {
    const user = userEvent.setup();
    renderProvider();
    await waitFor(() =>
      expect(screen.getByTestId('active-id')).toHaveTextContent('1'),
    );
    // The scoped query first ran for language 1.
    await waitFor(() => expect(scopedKeys).toContain(1));

    await user.click(screen.getByRole('button', { name: 'pick French' }));

    expect(screen.getByTestId('active-id')).toHaveTextContent('2');
    // Switching re-keyed the scoped query → it refetched for language 2.
    await waitFor(() => expect(scopedKeys).toContain(2));
    // And the choice is persisted for next time.
    expect(localStorage.getItem(activeLanguageStorageKey(USER_ID))).toBe('2');
  });

  it('exposes a refetch that re-runs the languages query (retryable error path)', async () => {
    const user = userEvent.setup();
    renderProvider();
    await waitFor(() =>
      expect(screen.getByTestId('active-id')).toHaveTextContent('1'),
    );

    await user.click(screen.getByRole('button', { name: 'retry languages' }));
    expect(languagesRefetch).toHaveBeenCalled();
  });

  it('stays unselected while the language list is still loading', async () => {
    useLanguagesQuery.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    });
    renderProvider();
    await waitFor(() =>
      expect(screen.getByTestId('active-id')).toHaveTextContent('none'),
    );
    expect(scopedKeys).not.toContain(1);
  });

  it('resolves to no active language for an empty account', async () => {
    useLanguagesQuery.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    });
    renderProvider();
    await waitFor(() =>
      expect(screen.getByTestId('active-id')).toHaveTextContent('none'),
    );
    expect(scopedKeys).not.toContain(1);
  });

  it('does not persist when there is no signed-in user', async () => {
    renderProvider(null);
    // No user id → no storage writes (and the picker stays in a no-selection state).
    await waitFor(() =>
      expect(screen.getByTestId('active-id')).toHaveTextContent('1'),
    );
    expect(localStorage.length).toBe(0);
  });
});
