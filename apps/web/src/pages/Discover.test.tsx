import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Drive the real discover/settings hooks against a mocked transport (GET /settings + POST /discover).
const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, getApiClient: () => ({ GET: get, POST: post }) };
});

import {
  ActiveLanguageContext,
  type ActiveLanguageState,
} from '@/components/active-language-context';
import { takeHandedOffWords } from '@/lib/generate-handoff';
import type { LanguageOut } from '@/lib/languages';
import Discover from '@/pages/Discover';

const SPANISH: LanguageOut = {
  id: 1,
  name: 'Spanish',
  code: 'es',
  vowelized: false,
};

interface ApiResult {
  data: unknown;
  error: unknown;
  response: Response;
}

function okResult(data: unknown, status = 200): Promise<ApiResult> {
  return Promise.resolve({
    data,
    error: undefined,
    response: new Response(null, { status }),
  });
}

function failResult(
  status: number,
  code: string,
  retryAfter?: number,
): Promise<ApiResult> {
  const headers =
    retryAfter !== undefined
      ? { 'Retry-After': String(retryAfter) }
      : undefined;
  return Promise.resolve({
    data: undefined,
    error: { code, message: `failed: ${code}` },
    response: new Response(null, { status, headers }),
  });
}

/** A `GET /settings` payload with the given discover_count (or none). */
function settingsPayload(discoverCount?: string): Promise<ApiResult> {
  return okResult({
    values:
      discoverCount !== undefined ? { discover_count: discoverCount } : {},
  });
}

function makeValue(
  overrides: Partial<ActiveLanguageState> = {},
): ActiveLanguageState {
  return {
    languages: [SPANISH],
    activeLanguageId: 1,
    activeLanguage: SPANISH,
    setActiveLanguageId: vi.fn(),
    isLoading: false,
    isError: false,
    ...overrides,
  };
}

function renderDiscover(value: ActiveLanguageState = makeValue()) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/discover']}>
        <ActiveLanguageContext.Provider value={value}>
          <Routes>
            <Route path="/discover" element={<Discover />} />
            <Route path="/generate" element={<div>GENERATE ROUTE</div>} />
          </Routes>
        </ActiveLanguageContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function countInput() {
  return screen.getByLabelText('How many words');
}

function discoverButton() {
  return screen.getByRole('button', { name: 'Discover' });
}

beforeEach(() => {
  vi.clearAllMocks();
  // Default: settings resolve with no saved discover_count → the form uses the server default (5).
  get.mockReturnValue(settingsPayload());
});

afterEach(() => {
  // The Discover → Generate handoff is module state; drain it so it never leaks between tests.
  takeHandedOffWords();
});

describe('Discover — language gating', () => {
  it('shows a loading state while languages load', () => {
    renderDiscover(
      makeValue({
        isLoading: true,
        activeLanguageId: null,
        activeLanguage: null,
      }),
    );
    expect(screen.getByText(/loading your languages/i)).toBeInTheDocument();
  });

  it('prompts to add a language when the user has none', () => {
    renderDiscover(makeValue({ activeLanguageId: null, activeLanguage: null }));
    expect(screen.getByText('Add a language first')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /add a language/i }),
    ).toHaveAttribute('href', '/languages');
  });

  it('names the active language in the intro copy', async () => {
    renderDiscover();
    expect(
      await screen.findByText(/example sentences in Spanish/i),
    ).toBeInTheDocument();
  });
});

describe('Discover — default count from settings (4.7.1)', () => {
  it('shows a settings-loading state before the form', () => {
    // A pending settings fetch keeps the workspace on its loading line.
    get.mockReturnValue(new Promise<ApiResult>(() => {}));
    renderDiscover();
    expect(screen.getByText(/loading your preferences/i)).toBeInTheDocument();
  });

  it("defaults the count to the user's discover_count setting", async () => {
    get.mockReturnValue(settingsPayload('7'));
    renderDiscover();
    expect(await screen.findByLabelText('How many words')).toHaveValue(7);
  });

  it('falls back to the server default when there is no setting', async () => {
    get.mockReturnValue(settingsPayload());
    renderDiscover();
    expect(await screen.findByLabelText('How many words')).toHaveValue(5);
  });

  it('clamps an out-of-range saved setting to the request bounds', async () => {
    get.mockReturnValue(settingsPayload('99'));
    renderDiscover();
    expect(await screen.findByLabelText('How many words')).toHaveValue(20);
  });
});

describe('Discover — count validation', () => {
  it('blocks discovery and warns when the count is out of range', async () => {
    renderDiscover();
    await screen.findByLabelText('How many words');

    fireEvent.change(countInput(), { target: { value: '0' } });
    expect(discoverButton()).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent(/between 1 and 20/i);

    // A blank value is invalid too.
    fireEvent.change(countInput(), { target: { value: '' } });
    expect(discoverButton()).toBeDisabled();

    // Back in range re-enables.
    fireEvent.change(countInput(), { target: { value: '6' } });
    expect(discoverButton()).toBeEnabled();
  });

  it('does not call the API for an out-of-range submit', async () => {
    renderDiscover();
    await screen.findByLabelText('How many words');
    fireEvent.change(countInput(), { target: { value: '0' } });
    fireEvent.submit(countInput().closest('form')!);
    expect(post).not.toHaveBeenCalled();
  });
});

describe('Discover — preview (4.7.1)', () => {
  it('previews suggested words and posts the count + null topic', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(okResult({ words: ['house', 'water', 'friend'] }));
    renderDiscover();
    await screen.findByLabelText('How many words');

    await user.click(discoverButton());

    const suggestions = await screen.findByTestId('discover-suggestions');
    expect(within(suggestions).getByText('house')).toBeInTheDocument();
    expect(within(suggestions).getByText('water')).toBeInTheDocument();
    expect(within(suggestions).getByText('friend')).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith('/discover', {
      body: { language_id: 1, count: 5, topic: null },
    });
  });

  it('includes a trimmed topic when one is entered', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(okResult({ words: ['house'] }));
    renderDiscover();
    await screen.findByLabelText('How many words');

    await user.type(screen.getByLabelText('Topic (optional)'), '  food  ');
    await user.click(discoverButton());

    await screen.findByTestId('discover-suggestions');
    expect(post).toHaveBeenCalledWith('/discover', {
      body: { language_id: 1, count: 5, topic: 'food' },
    });
  });

  it('shows the in-progress state while discovering', async () => {
    const user = userEvent.setup();
    let resolve!: (value: ApiResult) => void;
    post.mockReturnValue(
      new Promise<ApiResult>((res) => {
        resolve = res;
      }),
    );
    renderDiscover();
    await screen.findByLabelText('How many words');

    await user.click(discoverButton());
    expect(
      screen.getByRole('button', { name: /finding words/i }),
    ).toBeInTheDocument();
    expect(countInput()).toBeDisabled();

    resolve({
      data: { words: ['house'] },
      error: undefined,
      response: new Response(null, { status: 200 }),
    });
    expect(
      await screen.findByTestId('discover-suggestions'),
    ).toBeInTheDocument();
  });

  it('shows an empty state when no new words come back', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(okResult({ words: [] }));
    renderDiscover();
    await screen.findByLabelText('How many words');

    await user.click(discoverButton());
    expect(await screen.findByText('No new words found')).toBeInTheDocument();
    // Back to the form via "Change topic".
    await user.click(screen.getByRole('button', { name: /change topic/i }));
    expect(await screen.findByLabelText('How many words')).toBeInTheDocument();
  });

  it('shows a pending state on the empty panel while retrying', async () => {
    const user = userEvent.setup();
    let resolveRetry!: (value: ApiResult) => void;
    post.mockReturnValueOnce(okResult({ words: [] })).mockReturnValueOnce(
      new Promise<ApiResult>((res) => {
        resolveRetry = res;
      }),
    );
    renderDiscover();
    await screen.findByLabelText('How many words');

    await user.click(discoverButton());
    await screen.findByText('No new words found');
    await user.click(screen.getByRole('button', { name: /try again/i }));

    expect(
      screen.getByRole('button', { name: /finding/i }),
    ).toBeInTheDocument();

    resolveRetry({
      data: { words: ['house'] },
      error: undefined,
      response: new Response(null, { status: 200 }),
    });
    expect(
      await screen.findByTestId('discover-suggestions'),
    ).toBeInTheDocument();
  });
});

describe('Discover — reroll + accept (4.7.2)', () => {
  it('rerolls and replaces the suggested set with a fresh one', async () => {
    const user = userEvent.setup();
    post
      .mockReturnValueOnce(okResult({ words: ['house', 'water'] }))
      .mockReturnValueOnce(okResult({ words: ['music', 'river'] }));
    renderDiscover();
    await screen.findByLabelText('How many words');

    await user.click(discoverButton());
    expect(await screen.findByText('house')).toBeInTheDocument();

    await user.click(
      screen.getByRole('button', { name: /try different words/i }),
    );

    // The fresh set replaces the old one (a second POST went out).
    expect(await screen.findByText('music')).toBeInTheDocument();
    expect(screen.queryByText('house')).not.toBeInTheDocument();
    expect(post).toHaveBeenCalledTimes(2);
  });

  it('shows a pending state and disables actions while a reroll is in flight', async () => {
    const user = userEvent.setup();
    let resolveReroll!: (value: ApiResult) => void;
    post
      .mockReturnValueOnce(okResult({ words: ['house'] }))
      .mockReturnValueOnce(
        new Promise<ApiResult>((res) => {
          resolveReroll = res;
        }),
      );
    renderDiscover();
    await screen.findByLabelText('How many words');

    await user.click(discoverButton());
    await screen.findByTestId('discover-suggestions');
    await user.click(
      screen.getByRole('button', { name: /try different words/i }),
    );

    expect(
      screen.getByRole('button', { name: /finding/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Use these words' }),
    ).toBeDisabled();

    resolveReroll({
      data: { words: ['music'] },
      error: undefined,
      response: new Response(null, { status: 200 }),
    });
    expect(await screen.findByText('music')).toBeInTheDocument();
  });

  it('accepting hands the words into the Generate flow and navigates there', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(okResult({ words: ['house', 'water'] }));
    renderDiscover();
    await screen.findByLabelText('How many words');

    await user.click(discoverButton());
    await screen.findByTestId('discover-suggestions');

    await user.click(screen.getByRole('button', { name: 'Use these words' }));

    // Routed into the Generate flow…
    expect(await screen.findByText('GENERATE ROUTE')).toBeInTheDocument();
    // …with the suggested words handed off to it.
    expect(takeHandedOffWords()).toEqual(['house', 'water']);
  });

  it('returns to the form (clearing suggestions) on Start over', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(okResult({ words: ['house'] }));
    renderDiscover();
    await screen.findByLabelText('How many words');

    await user.click(discoverButton());
    await screen.findByTestId('discover-suggestions');

    await user.click(screen.getByRole('button', { name: /start over/i }));
    expect(await screen.findByLabelText('How many words')).toBeInTheDocument();
    expect(
      screen.queryByTestId('discover-suggestions'),
    ).not.toBeInTheDocument();
  });
});

describe('Discover — friendly cost-guard states (4.7.3)', () => {
  it('renders the shared daily-limit panel for a quota 429 (not a generic error)', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(failResult(429, 'daily_limit_reached'));
    renderDiscover();
    await screen.findByLabelText('How many words');
    fireEvent.change(countInput(), { target: { value: '8' } });

    await user.click(discoverButton());

    expect(await screen.findByTestId('daily-limit-panel')).toBeInTheDocument();
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
    // The form (and the entered count) is preserved.
    expect(countInput()).toHaveValue(8);
  });

  it('renders the daily-limit panel for the per-user cap shape too', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(failResult(429, 'daily_cap_reached'));
    renderDiscover();
    await screen.findByLabelText('How many words');

    await user.click(discoverButton());
    expect(await screen.findByTestId('daily-limit-panel')).toBeInTheDocument();
  });

  it('renders the daily-limit panel when a reroll hits the quota', async () => {
    const user = userEvent.setup();
    post
      .mockReturnValueOnce(okResult({ words: ['house'] }))
      .mockReturnValueOnce(failResult(429, 'daily_limit_reached'));
    renderDiscover();
    await screen.findByLabelText('How many words');

    await user.click(discoverButton());
    await screen.findByTestId('discover-suggestions');
    await user.click(
      screen.getByRole('button', { name: /try different words/i }),
    );

    expect(await screen.findByTestId('daily-limit-panel')).toBeInTheDocument();
  });

  it('renders a friendly transient state for server_busy (not the daily panel)', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(failResult(503, 'server_busy', 3));
    renderDiscover();
    await screen.findByLabelText('How many words');

    await user.click(discoverButton());
    expect(await screen.findByText('The server is busy')).toBeInTheDocument();
    expect(
      screen.getByText(/press Discover to try again/i),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('daily-limit-panel')).not.toBeInTheDocument();
  });

  it('renders a generic error for an unclassified failure', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(failResult(500, 'kaboom'));
    renderDiscover();
    await screen.findByLabelText('How many words');

    await user.click(discoverButton());
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('Something went wrong')).toBeInTheDocument();
  });
});
